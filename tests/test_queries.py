from pathlib import Path

from market_brief.analytics import available_queries


def test_all_seven_query_files_are_present() -> None:
    queries = available_queries()
    assert len(queries) == 7
    assert [item.name for item in queries] == [f"{i:02d}_{name}.sql" for i, name in [
        (1, "returns"), (2, "gainers_losers"), (3, "volume_spikes"), (4, "vwap"),
        (5, "sector_performance"), (6, "gaps"), (7, "52_week_extremes"),
    ]]
    assert all("%(as_of)s" in Path(query).read_text() for query in queries)
