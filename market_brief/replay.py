"""Replay historical sessions through Ollama and record numeric-validator outcomes."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from .analytics import run_queries
from .brief import llm_brief
from .config import settings
from .db import query
from .validate import ValidationError, validate_numeric_claims

LOGGER = logging.getLogger(__name__)


def available_sessions(end_as_of: date, count: int) -> list[date]:
    rows = query(
        """SELECT DISTINCT trading_date FROM daily_bars
           WHERE trading_date <= %s ORDER BY trading_date DESC LIMIT %s""",
        (end_as_of, count),
    )
    return sorted(row["trading_date"] for row in rows)


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
            outcomes.append({"as_of": as_of.isoformat(), "status": "rejected", "detail": str(exc)})
        except Exception as exc:
            LOGGER.exception("Ollama replay failed for %s", as_of)
            outcomes.append({"as_of": as_of.isoformat(), "status": "error", "detail": str(exc)})
        else:
            LOGGER.info("Ollama draft accepted for %s", as_of)
            outcomes.append({"as_of": as_of.isoformat(), "status": "accepted", "detail": ""})

    accepted = sum(row["status"] == "accepted" for row in outcomes)
    rejected = sum(row["status"] == "rejected" for row in outcomes)
    errors = sum(row["status"] == "error" for row in outcomes)
    return {
        "model": settings().ollama_model,
        "end_as_of": end_as_of.isoformat(),
        "attempted_sessions": len(outcomes),
        "drafts_returned": accepted + rejected,
        "accepted": accepted,
        "rejected": rejected,
        "errors": errors,
        "outcomes": outcomes,
    }


def write_replay_report(report: dict[str, object], destination: Path) -> Path:
    """Persist aggregate evidence and per-session statuses, never raw model text."""
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
        "| Session | Outcome | Detail |",
        "| --- | --- | --- |",
    ]
    for row in report["outcomes"]:  # type: ignore[index]
        detail = str(row["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['as_of']} | {row['status']} | {detail} |")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
