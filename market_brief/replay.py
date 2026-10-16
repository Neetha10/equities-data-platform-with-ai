"""Replay historical sessions through Ollama and record numeric-validator outcomes."""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from .analytics import run_queries
from .brief import llm_brief
from .config import settings
from .db import query
from .validate import (
    NUMBER,
    ValidationError,
    _absolute_number,
    _numbers_by_symbol,
    _sentence,
    validate_numeric_claims,
)

LOGGER = logging.getLogger(__name__)


def available_sessions(end_as_of: date, count: int) -> list[date]:
    rows = query(
        """SELECT DISTINCT trading_date FROM daily_bars
           WHERE trading_date <= %s ORDER BY trading_date DESC LIMIT %s""",
        (end_as_of, count),
    )
    return sorted(row["trading_date"] for row in rows)


NEAR_MISS = Decimal("0.05")
REJECTED_TOKENS = re.compile(r"absent from query results: (.+)$")


def _ledger_values(results: dict[str, list[dict]]) -> list[Decimal]:
    values = {value for numbers in _numbers_by_symbol(results).values() for value in numbers}
    for rows in results.values():
        for row in rows:
            if "symbol" not in row:
                values.update(v for v in (_absolute_number(x) for x in row.values()) if v is not None)
    return [Decimal(value) for value in values]


def classify_rejection(token: str, sentence: str, results: dict[str, list[dict]]) -> str:
    """Best-effort label for one rejected number, to be confirmed by reading the sentence."""
    value = _absolute_number(token)
    if value is None:
        return "unparsed"
    by_symbol = _numbers_by_symbol(results)
    owners = {symbol for symbol, numbers in by_symbol.items() if value in numbers}
    in_sentence = {symbol for symbol in by_symbol if re.search(rf"(?<![A-Z]){re.escape(symbol)}(?![A-Z])", sentence)}
    if owners & in_sentence:
        return "likely validator false positive"
    if owners:
        return "number from another ticker"
    if any(abs(Decimal(value) - known) <= NEAR_MISS for known in _ledger_values(results)):
        return "model changed a digit"
    return "invented number"


def explain_rejection(draft: str, error: ValidationError, results: dict[str, list[dict]]) -> list[dict[str, str]]:
    """Return the offending sentence and a label for every number the validator rejected."""
    match = REJECTED_TOKENS.search(str(error))
    tokens = [token.strip() for token in match.group(1).split(",")] if match else []
    found: list[dict[str, str]] = []
    for token in tokens:
        hit = next((m for m in NUMBER.finditer(draft) if m.group() == token), None)
        sentence = _sentence(draft, hit.start())[1].strip() if hit else ""
        found.append({"number": token, "label": classify_rejection(token, sentence, results), "sentence": sentence})
    return found


def replay_ollama(end_as_of: date, count: int) -> dict[str, object]:
    """Generate one raw local-model draft per completed session without overwriting briefs."""
    if count < 1:
        raise ValueError("count must be positive")
    if settings().llm_provider != "ollama":
        raise RuntimeError("set LLM_PROVIDER=ollama before replaying local-model drafts")

    outcomes: list[dict[str, str]] = []
    for as_of in available_sessions(end_as_of, count):
        try:
            results = run_queries(as_of)
            draft = llm_brief(results, as_of)
            validate_numeric_claims(draft, results, as_of)
        except ValidationError as exc:
            LOGGER.warning("Ollama draft rejected for %s: %s", as_of, exc)
            for item in explain_rejection(draft, exc, results):
                outcomes.append({"as_of": as_of.isoformat(), "status": "rejected", "detail": item["number"],
                                 "label": item["label"], "sentence": item["sentence"]})
        except Exception as exc:
            LOGGER.exception("Ollama replay failed for %s", as_of)
            outcomes.append({"as_of": as_of.isoformat(), "status": "error", "detail": str(exc)})
        else:
            LOGGER.info("Ollama draft accepted for %s", as_of)
            outcomes.append({"as_of": as_of.isoformat(), "status": "accepted", "detail": ""})

    sessions = {row["as_of"]: row["status"] for row in outcomes}
    accepted = sum(status == "accepted" for status in sessions.values())
    rejected = sum(status == "rejected" for status in sessions.values())
    errors = sum(status == "error" for status in sessions.values())
    labels = Counter(row["label"] for row in outcomes if row["status"] == "rejected")
    return {
        "model": settings().ollama_model,
        "end_as_of": end_as_of.isoformat(),
        "attempted_sessions": len(sessions),
        "drafts_returned": accepted + rejected,
        "accepted": accepted,
        "rejected": rejected,
        "errors": errors,
        "labels": dict(labels),
        "outcomes": outcomes,
    }


def write_replay_report(report: dict[str, object], destination: Path) -> Path:
    """Persist aggregate evidence plus the single sentence behind each rejected number."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Ollama replay validation report",
        "",
        f"- Model: `{report['model']}`",
        f"- Last session: {report['end_as_of']}",
        f"- Sessions attempted: {report['attempted_sessions']}",
        f"- Drafts returned: {report['drafts_returned']}",
        f"- Accepted: {report['accepted']}",
        f"- Rejected by numeric validator: {report['rejected']}",
        f"- Provider/analysis errors: {report['errors']}",
        "",
        "Rejected numbers by automatic label (confirm each by reading its sentence):",
        "",
    ]
    for label, total in sorted(report.get("labels", {}).items()):  # type: ignore[union-attr]
        lines.append(f"- {label}: {total}")
    lines += ["", "| Session | Outcome | Number | Label | Sentence |", "| --- | --- | --- | --- | --- |"]
    for row in report["outcomes"]:  # type: ignore[index]
        cells = [row["as_of"], row["status"], row.get("detail", ""), row.get("label", ""), row.get("sentence", "")]
        lines.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
