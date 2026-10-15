from market_brief.ingest import load_universe


def test_seed_universe_has_one_hundred_unique_symbols() -> None:
    symbols = load_universe()
    assert len(symbols) == 100
    assert len(set(symbols)) == len(symbols)
