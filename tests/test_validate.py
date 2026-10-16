from datetime import date
from decimal import Decimal

import pytest

from market_brief import brief
from market_brief.brief import deterministic_brief
from market_brief.validate import ValidationError, validate_numeric_claims


@pytest.fixture
def results() -> dict[str, list[dict]]:
    return {
        "02_gainers_losers": [
            {"direction": "gainer", "symbol": "AAA", "close": Decimal("101.1"), "return_pct": Decimal("2.25")},
            {"direction": "loser", "symbol": "BBB", "close": Decimal(90), "return_pct": Decimal("-1.2")},
        ],
        "03_volume_spikes": [{"symbol": "CCC", "volume_multiple": Decimal("3.1")}],
        "05_sector_performance": [
            {"sector": "Tech", "equal_weight_return_pct": Decimal("1.2")},
            {"sector": "Energy", "equal_weight_return_pct": Decimal("-0.8")},
        ],
        "06_gaps": [{"symbol": "DDD", "gap_pct": Decimal("4.5")}],
    }


def test_deterministic_brief_is_verifiable(results: dict[str, list[dict]]) -> None:
    as_of = date(2026, 10, 15)
    text = deterministic_brief(results, as_of)
    validate_numeric_claims(text, results, as_of)


def test_hallucinated_number_is_rejected(results: dict[str, list[dict]]) -> None:
    with pytest.raises(ValidationError, match="999"):
        validate_numeric_claims("AAA rose 999%.", results, date(2026, 10, 15))


def test_rejects_numbers_borrowed_from_a_different_ticker(results: dict[str, list[dict]]) -> None:
    with pytest.raises(ValidationError, match="6.59"):
        validate_numeric_claims("AAA led at 6.59%, while BBB was weakest at 2.25%.", results, date(2026, 10, 15))


def test_rejects_date_and_query_constant_numbers(results: dict[str, list[dict]]) -> None:
    with pytest.raises(ValidationError, match="15, 10, 5"):
        validate_numeric_claims("AAA jumped 15%. BBB fell 10%. CCC traded 5x normal volume.", results, date(2026, 10, 15))


def test_accepts_natural_language_without_a_negative_sign(results: dict[str, list[dict]]) -> None:
    validate_numeric_claims("BBB fell 1.20%.", results, date(2026, 10, 15))


def test_rejection_is_logged_and_falls_back(monkeypatch, caplog, results: dict[str, list[dict]], tmp_path) -> None:
    monkeypatch.setattr(brief, "llm_brief", lambda *_: "AAA rose 999%.")
    monkeypatch.setattr(brief, "llm_is_configured", lambda: True)
    _, _, accepted = brief.create_brief(results, date(2026, 10, 15), tmp_path)
    assert not accepted
    assert "LLM draft rejected by numeric validation" in caplog.text
