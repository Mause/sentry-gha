import logging
import os
from functools import wraps
from typing import Callable

import sentry_sdk
from rich.console import Console
from rich.logging import RichHandler
from ruamel.yaml import YAML
from sentry_sdk.crons import monitor as _monitor

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


def init(spotlight: bool = False) -> None:
    github_ref_name = os.getenv("GITHUB_REF_NAME")
    if github_ref_name is None:
        environment = "development"
    elif github_ref_name == "main":
        environment = "production"
    else:
        environment = "staging"

    sentry_sdk.init(
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        # Enable sending logs to Sentry
        enable_logs=True,
        environment=environment,
        release=os.getenv("GITHUB_SHA", "unknown"),
        spotlight=spotlight,
    )

    scope = sentry_sdk.get_current_scope()
    scope.set_tag("GITHUB_REF_NAME", github_ref_name)

    client = sentry_sdk.get_current_scope().get_client()
    print(
        "Sentry is",
        "enabled" if client.is_active() and client.transport else "disabled",
    )


def monitor[F: Callable, R, **P](
    monitor_slug: str, workflow_name: str
) -> Callable[[F], F]:
    with open(f".github/workflows/{workflow_name}.yml") as fh:
        action = YAML().load(fh)

    schedule = action["on"]["schedule"][0]["cron"]

    def wrapper(func: F) -> F:
        @_monitor(
            monitor_slug,
            {
                "schedule": {
                    "type": "crontab",
                    "value": schedule,
                }
            },
        )
        @wraps(func)
        def decorator(*args: P.args, **kwargs: P.kwargs) -> R:
            transaction = sentry_sdk.start_transaction(
                op="task",
                name=monitor_slug,
            )
            with transaction:
                return func(*args, **kwargs)

        return decorator

    return wrapper
