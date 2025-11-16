import json
from typing import Callable

from pytest import MonkeyPatch
from sentry_sdk.api import get_client
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport
from syrupy.session import SnapshotSession

import sentry_gha
from sentry_gha import init, monitor


def make_subject() -> Callable[[int, int], int]:
    @monitor("sentry_gha-w4", "python-app")
    def my_function(x: int, y: int) -> int:
        return x + y

    return my_function


class DummyTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.envelopes = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)


def test_monitor(monkeypatch: MonkeyPatch, snapshot: SnapshotSession) -> None:
    monkeypatch.setattr(sentry_gha, "get_cron_schedule", lambda wn: "*/5 * * * *")
    monkeypatch.setenv("SENTRY_DSN", "http://u:u@example.com/123")

    my_function = make_subject()

    transport = DummyTransport()
    init(transport=transport)

    client = get_client()

    with client:
        result = my_function(2, 3)
        assert result == 5

    datum = [
        [json.loads(item) for item in e.serialize().splitlines()]
        for e in transport.envelopes
    ]
    assert snapshot == wipe(datum)


def wipe(data: list | dict | str | int | None) -> list | dict | str | int | None:
    if isinstance(data, list):
        return [wipe(item) for item in data]
    elif isinstance(data, dict):
        new = {}
        for key, value in data.items():
            if key in (
                "event_id",
                "trace_id",
                "check_in_id",
                "span_id",
                "timestamp",
                "sent_at",
                "duration",
                "thread.id",
                "server_name",
                "sample_rand",
                "environment",
                "release",
                "start_timestamp",
                "length",
                "build",
                "sys.argv",
                "version",
                "GITHUB_REF_NAME",
            ):
                new[key] = key
            else:
                new[key] = wipe(value)
        return new
    elif isinstance(data, (str, int, float, type(None))):
        return data
    else:
        raise NotImplementedError((data, type(data)))
