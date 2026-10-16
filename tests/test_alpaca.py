from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import requests

from market_brief import alpaca


def test_sip_end_is_capped_to_delayed_boundary(monkeypatch) -> None:
    monkeypatch.setattr(alpaca, "settings", lambda: SimpleNamespace(alpaca_feed="sip"))
    capped = alpaca._cap_sip_end(datetime.now(UTC) + timedelta(days=1))
    assert isinstance(capped, datetime)
    assert capped <= datetime.now(UTC) - timedelta(minutes=15)


def test_iex_end_is_unchanged(monkeypatch) -> None:
    value = datetime(2026, 10, 15, 20, tzinfo=UTC)
    monkeypatch.setattr(alpaca, "settings", lambda: SimpleNamespace(alpaca_feed="iex"))
    assert alpaca._cap_sip_end(value) == value


def test_bars_follows_page_tokens(monkeypatch) -> None:
    pages = [
        {"bars": {"AAA": [{"t": "2026-10-14T00:00:00+00:00", "c": 1}]}, "next_page_token": "next"},
        {"bars": {"AAA": [{"t": "2026-10-15T00:00:00+00:00", "c": 2}]}},
    ]
    requests_seen: list[dict] = []

    class Response:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return pages.pop(0)

    def fake_get(*_, params, **__) -> Response:
        requests_seen.append(params.copy())
        return Response()

    monkeypatch.setattr(
        alpaca,
        "settings",
        lambda: SimpleNamespace(alpaca_feed="iex", alpaca_api_key="key", alpaca_api_secret="secret"),
    )
    monkeypatch.setattr(requests, "get", fake_get)
    rows = list(alpaca.bars(["AAA"], "1Day", datetime(2026, 10, 14, tzinfo=UTC), datetime(2026, 10, 16, tzinfo=UTC)))
    assert [row["c"] for row in rows] == [1, 2]
    assert requests_seen[1]["page_token"] == "next"
