import inspect
import logging
import os
import warnings
from datetime import timedelta
from functools import wraps
from typing import Callable

import sentry_sdk
from cron_converter import Cron
from rich.console import Console
from rich.logging import RichHandler
from ruamel.yaml import YAML
from sentry_sdk.api import capture_exception, start_transaction
from sentry_sdk.crons import monitor as _monitor
from sentry_sdk.transport import Transport
from sentry_sdk.types import MonitorConfig
from sentry_sdk.utils import qualname_from_function

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        RichHandler(
            console=Console(
                width=120,
            )
        )
    ],
)

__all__ = ["monitor", "init"]


def init(spotlight: bool = False, transport: Transport | None = None) -> None:
    github_ref_name = os.getenv("GITHUB_REF_NAME")
    if github_ref_name is None:
        environment = "development"
    elif github_ref_name == "main":
        environment = "production"
    else:
        environment = "staging"

    sentry_sdk.init(
        # Add data like request headers and IP for users,
        # see
        # https://docs.sentry.io/platforms/python/data-management/data-collected/
        # for more info
        send_default_pii=True,
        # Enable sending logs to Sentry
        enable_logs=True,
        environment=environment,
        release=os.getenv("GITHUB_SHA", "unknown"),
        traces_sample_rate=1.0,
        spotlight=spotlight,
        transport=transport,
    )

    scope = sentry_sdk.get_current_scope()
    scope.set_tag("GITHUB_REF_NAME", github_ref_name)

    client = sentry_sdk.get_current_scope().get_client()
    print(
        "Sentry is",
        "enabled" if client.is_active() and client.transport else "disabled",
    )


def get_cron_schedule(workflow_name: str) -> str:
    with open(f".github/workflows/{workflow_name}.yml") as fh:
        action = YAML().load(fh)

    schedule = action["on"]["schedule"][0]["cron"]

    parsed = Cron(schedule)
    minute = parsed.parts[0]
    assert minute.unit["name"] == "minute"
    if minute.has(0):
        warnings.warn(f"GitHub recommends that jobs not run on the hour: {schedule}")

    return schedule


FIVE_MINUTES = timedelta(minutes=5).total_seconds() / 60.0
TEN_MINUTES = timedelta(minutes=10).total_seconds() / 60.0
OPERATION = "function"


def monitor[F: Callable, R, **P](
    monitor_slug: str, workflow_name: str
) -> Callable[[F], F]:
    schedule = get_cron_schedule(workflow_name)

    def wrapper(func: F) -> F:
        m: MonitorConfig = {
            "schedule": {
                "type": "crontab",
                "value": schedule,
            },
            "max_runtime": FIVE_MINUTES,
            "checkin_margin": TEN_MINUTES,
            "timezone": "Australia/Perth",
        }
        dec = _monitor(
            monitor_slug,
            m,
        )
        function_name = qualname_from_function(func) or ""

        @dec
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with start_transaction(
                op=OPERATION,
                name=function_name,
            ):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    capture_exception(e)
                    raise

        try:
            async_wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
        except Exception:
            pass

        @dec
        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with start_transaction(
                op=OPERATION,
                name=function_name,
            ):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    capture_exception(e)
                    raise

        try:
            sync_wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
        except Exception:
            pass

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return wrapper
