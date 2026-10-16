from market_brief.edgar import sec_sector


def test_sector_overrides_prevent_broad_manufacturing_bucket() -> None:
    assert sec_sector("3571", "AAPL") == "Information Technology"
    assert sec_sector("2911", "XOM") == "Energy"
    assert sec_sector("2834", "LLY") == "Health Care"


def test_sic_ranges_are_gics_style_not_single_manufacturing_bucket() -> None:
    assert sec_sector("2834") == "Health Care"
    assert sec_sector("3674") == "Information Technology"
    assert sec_sector("4911") == "Utilities"
