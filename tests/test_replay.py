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


def _ledger() -> dict[str, list[dict]]:
    from decimal import Decimal

    return {
        "02_gainers_losers": [
            {"direction": "gainer", "symbol": "NOW", "return_pct": Decimal("6.15")},
            {"direction": "loser", "symbol": "DELL", "return_pct": Decimal("-6.59")},
        ],
        "06_gaps": [{"symbol": "AMD", "gap_pct": Decimal("12.14")}],
    }


def test_classifies_each_kind_of_rejection() -> None:
    ledger = _ledger()
    assert replay.classify_rejection("6.14", "NOW led at 6.14%.", ledger) == "model changed a digit"
    assert replay.classify_rejection("6.59", "NOW fell 6.59%.", ledger) == "number from another ticker"
    assert replay.classify_rejection("12.14", "AMD and NOW moved, with a 12.14% gap.", ledger) == (
        "likely validator false positive"
    )
    assert replay.classify_rejection("42.00", "NOW rose 42.00%.", ledger) == "invented number"


def test_rejected_sentence_is_recorded(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(replay, "settings", lambda: SimpleNamespace(llm_provider="ollama", ollama_model="llama3.2:3b"))
    monkeypatch.setattr(replay, "query", lambda *_: [{"trading_date": date(2026, 10, 15)}])
    monkeypatch.setattr(replay, "run_queries", lambda as_of: _ledger())
    monkeypatch.setattr(replay, "llm_brief", lambda *_: "Markets were mixed. NOW led at 6.14% today.")
    report = replay.replay_ollama(date(2026, 10, 15), 1)
    assert report["rejected"] == 1 and report["labels"] == {"model changed a digit": 1}
    text = replay.write_replay_report(report, tmp_path / "r.md").read_text()
    assert "NOW led at 6.14% today" in text and "Markets were mixed" not in text
