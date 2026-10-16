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


def test_keeps_decimal_claim_and_ticker_in_the_same_sentence() -> None:
    ledger = {
        "01_returns": [{"symbol": "DELL", "return_pct": Decimal("-6.59")}],
        "03_volume_spikes": [{"symbol": "DELL", "volume_multiple": Decimal("3.24")}],
    }
    validate_numeric_claims("DELL fell 6.59% on 3.24x its usual volume.", ledger, date(2026, 10, 15))


def test_validates_multiple_decimal_claims_with_their_nearest_tickers() -> None:
    ledger = {
        "01_returns": [
            {"symbol": "NOW", "return_pct": Decimal("6.15")},
            {"symbol": "DELL", "return_pct": Decimal("-6.59")},
        ]
    }
    validate_numeric_claims(
        "Shares closed up 6.15% for NOW, and DELL dropped 6.59%.", ledger, date(2026, 10, 15)
    )


def test_rejection_is_logged_and_falls_back(monkeypatch, caplog, results: dict[str, list[dict]], tmp_path) -> None:
    monkeypatch.setattr(brief, "llm_brief", lambda *_: "AAA rose 999%.")
    monkeypatch.setattr(brief, "llm_is_configured", lambda: True)
    _, _, accepted = brief.create_brief(results, date(2026, 10, 15), tmp_path)
    assert not accepted
    assert "LLM draft rejected by numeric validation" in caplog.text


REPLAY_LEDGER = {
    "02_gainers_losers": [
        {"direction": "gainer", "symbol": "LRCX", "return_pct": Decimal("6.98")},
        {"direction": "loser", "symbol": "QCOM", "return_pct": Decimal("-5.82")},
        {"direction": "gainer", "symbol": "CCI", "return_pct": Decimal("15.60")},
        {"direction": "loser", "symbol": "CHTR", "return_pct": Decimal("-5.74")},
    ],
}


@pytest.mark.parametrize(
    "sentence",
    [
        # Real llama3.2:3b sentences that were wrongly rejected in the 20-session replay.
        "LRCX led the market at 6.98%, while QCOM was weakest at -5.82%.",
        "CCI led the market with a 15.60% gain, while CHTR posted a -5.74% loss.",
    ],
)
def test_number_belongs_to_the_ticker_before_it(sentence: str) -> None:
    validate_numeric_claims(sentence, REPLAY_LEDGER, date(2026, 10, 15))


def test_swapped_tickers_in_long_sentence_still_rejected() -> None:
    with pytest.raises(ValidationError, match="6.98"):
        validate_numeric_claims(
            "QCOM led the market at 6.98%, while LRCX was weakest at -5.82%.", REPLAY_LEDGER, date(2026, 10, 15)
        )
