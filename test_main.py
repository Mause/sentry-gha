import json
from contextlib import contextmanager
from io import StringIO
from typing import Callable, Generator
from unittest.mock import patch

from pytest import MonkeyPatch, warns
from ruamel.yaml import YAML
from sentry_sdk.api import get_client
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport
from syrupy.session import SnapshotSession

from sentry_gha import init, monitor


def make_subject(cron: str) -> Callable[[int, int], int]:
    fh = StringIO()
    YAML().dump(
        {"on": {"schedule": [{"cron": cron}]}},
        fh,
    )
    fh.seek(0)

    with patch("builtins.open", return_value=fh):

        @monitor("sentry_gha-w4", "python-app")
        def my_function(x: int, y: int) -> int:
            return x // y

    return my_function


class DummyTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.envelopes = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)


def test_warning() -> None:
    with warns(UserWarning, match="on the hour"):
        make_subject("* * * * *")


def test_monitor(monkeypatch: MonkeyPatch, snapshot: SnapshotSession) -> None:
    my_function = make_subject("10-55/5 * * * *")

    with catch(monkeypatch) as datum:
        assert my_function(10, 2) == 5

    assert snapshot == wipe(datum)


@contextmanager
def catch(monkeypatch: MonkeyPatch) -> Generator[list, None, None]:
    monkeypatch.setenv("SENTRY_DSN", "http://u:u@example.com/123")
    transport = DummyTransport()
    init(transport=transport)

    datum = []
    with get_client():
        yield datum

    datum.extend(
        [json.loads(item) for item in e.serialize().splitlines()]
        for e in transport.envelopes
    )


def wipe(data: list | dict | str | int | None) -> list | dict | str | int | None:
    if isinstance(data, list):
        return [wipe(item) for item in data]
    elif isinstance(data, dict):
        new = {}
        for key, value in data.items():
            if key in {"timestamp", "sent_at", "start_timestamp"}:
                new[key] = "<redacted-timestamp>"
            elif key in {
                "event_id",
                "trace_id",
                "check_in_id",
                "span_id",
            }:
                new[key] = "<redacted-id>"
            elif key in (
                "duration",
                "thread.id",
                "server_name",
                "sample_rand",
                "environment",
                "release",
                "length",
                "build",
                "sys.argv",
                "version",
                "GITHUB_REF_NAME",
            ):
                new[key] = {
                    int: 0,
                    float: 0.0,
                }.get(type(value), key)
            else:
                new[key] = wipe(value)
        return new
    elif isinstance(data, (str, int, float, type(None))):
        return data
    else:
        raise NotImplementedError((data, type(data)))
