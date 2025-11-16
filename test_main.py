import _pytest.monkeypatch
from _pytest.monkeypatch import MonkeyPatch
from sentry_sdk.api import get_client

import sentry_gha
from sentry_gha import init, monitor


def make_subject() -> None:
    @monitor("sentry_gha-w4", "python-app")
    def my_function(x: int, y: int) -> int:
        return x + y

    return my_function


def test_monitor(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(sentry_gha, "get_cron_schedule", lambda wn: "*/5 * * * *")
    monkeypatch.setenv("SENTRY_DSN", "http://u:u@example.com/123")

    my_function = make_subject()

    init(transport=1)

    client = get_client()

    with client:
        result = my_function(2, 3)
        assert result == 5
        breakpoint()
