from typing import Callable

from pytest import MonkeyPatch
from sentry_sdk.api import get_client
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

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


def test_monitor(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(sentry_gha, "get_cron_schedule", lambda wn: "*/5 * * * *")
    monkeypatch.setenv("SENTRY_DSN", "http://u:u@example.com/123")

    my_function = make_subject()

    transport = DummyTransport()
    init(transport=transport)

    client = get_client()

    with client:
        result = my_function(2, 3)
        assert result == 5
        breakpoint()

    assert len(transport.envelopes) == 1
