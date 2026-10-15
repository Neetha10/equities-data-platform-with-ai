from datetime import date
from decimal import Decimal

import pytest

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
