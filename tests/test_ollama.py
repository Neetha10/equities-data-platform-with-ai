from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import requests

from market_brief import brief


def test_ollama_rewrites_an_approved_brief(monkeypatch) -> None:
    results = {
        "02_gainers_losers": [
            {"direction": "gainer", "symbol": "AAA", "return_pct": Decimal("2.25")},
            {"direction": "loser", "symbol": "BBB", "return_pct": Decimal("-1.2")},
        ],
        "03_volume_spikes": [{"symbol": "CCC", "volume_multiple": Decimal("3.1")}],
        "05_sector_performance": [
            {"sector": "Tech", "equal_weight_return_pct": Decimal("1.2")},
            {"sector": "Energy", "equal_weight_return_pct": Decimal("-0.8")},
        ],
        "06_gaps": [{"symbol": "DDD", "gap_pct": Decimal("4.5")}],
    }
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            return {"response": "# US Equities Close — 2026-10-15\n\nVerified local rewrite."}

    def fake_post(url: str, **kwargs: object) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    config = SimpleNamespace(
        llm_provider="ollama",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="llama3.2:3b",
    )
    monkeypatch.setattr(brief, "settings", lambda: config)
    monkeypatch.setattr(requests, "post", fake_post)

    response = brief.llm_brief(results, date(2026, 10, 15))

    assert response.endswith("Verified local rewrite.")
    assert captured["url"] == "http://127.0.0.1:11434/api/generate"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["stream"] is False
    assert "APPROVED BRIEF:" in str(payload["prompt"])
    assert "AAA at 2.25%" in str(payload["prompt"])
