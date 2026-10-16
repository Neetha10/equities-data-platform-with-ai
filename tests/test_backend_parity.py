import os
from datetime import date, datetime
from decimal import Decimal

import pytest

from market_brief.analytics import run_queries

pytestmark = pytest.mark.integration


def _normalized(value: object) -> object:
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return Decimal(str(value)).normalize()
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _rows(rows: list[dict]) -> list[dict]:
    return sorted([{key: _normalized(value) for key, value in row.items()} for row in rows], key=str)


@pytest.mark.skipif(not os.getenv("RUN_DB_INTEGRATION"), reason="set RUN_DB_INTEGRATION=1 with PostgreSQL running")
def test_all_seven_engine_results_match_postgres_snapshot() -> None:
    as_of = date(2026, 10, 15)
    engine = run_queries(as_of, backend="engine")
    postgres = run_queries(as_of, backend="postgres")
    assert set(engine) == set(postgres) == {
        "01_returns",
        "02_gainers_losers",
        "03_volume_spikes",
        "04_vwap",
        "05_sector_performance",
        "06_gaps",
        "07_52_week_extremes",
    }
    for name in engine:
        assert _rows(engine[name]) == _rows(postgres[name]), name
