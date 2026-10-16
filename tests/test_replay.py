from datetime import date
from types import SimpleNamespace

from market_brief import replay


def test_replay_counts_validator_rejections_and_writes_report(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(replay, "settings", lambda: SimpleNamespace(llm_provider="ollama", ollama_model="llama3.2:3b"))
    monkeypatch.setattr(
        replay,
        "query",
        lambda *_: [{"trading_date": date(2026, 10, 14)}, {"trading_date": date(2026, 10, 15)}],
    )
    monkeypatch.setattr(replay, "run_queries", lambda as_of: {"facts": [{"symbol": "AAA", "return_pct": 1}]})
    monkeypatch.setattr(replay, "llm_brief", lambda _, as_of: "AAA rose 1%." if as_of.day == 14 else "AAA rose 999%.")
    report = replay.replay_ollama(date(2026, 10, 15), 2)
    assert report["accepted"] == 1
    assert report["rejected"] == 1
    assert report["errors"] == 0
    saved = replay.write_replay_report(report, tmp_path / "replay.md")
    assert "Rejected by numeric validator: 1" in saved.read_text()
