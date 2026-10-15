import csv
import logging
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from . import alpaca
from .config import settings
from .db import connection, execute_values
from .edgar import upsert_companies

LOGGER = logging.getLogger(__name__)


def load_universe(path: str | Path = "data/universe.csv") -> list[str]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [row["symbol"].strip().upper() for row in csv.DictReader(handle) if row["symbol"].strip()]


def _run_started(kind: str) -> int:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO ingestion_runs (run_type, status) VALUES (%s, 'running') RETURNING id", (kind,))
        return cur.fetchone()["id"]


def _run_finished(run_id: int, written: int, error: str | None = None) -> None:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE ingestion_runs SET completed_at = now(), status = %s, rows_written = %s,
               details = CASE WHEN %s::text IS NULL THEN details
                              ELSE jsonb_build_object('error', %s::text) END
               WHERE id = %s""",
            ("failed" if error else "succeeded", written, error, error, run_id),
        )


def _daily_rows(records: list[dict]) -> list[tuple]:
    feed = settings().alpaca_feed
    return [
        (
            row["symbol"], datetime.fromisoformat(row["t"]).date(),
            row["o"], row["h"], row["l"], row["c"], row["v"], row.get("n"), row.get("vw"), feed,
        )
        for row in records
    ]


def _minute_rows(records: list[dict]) -> list[tuple]:
    feed = settings().alpaca_feed
    return [
        (
            row["symbol"], datetime.fromisoformat(row["t"]),
            row["o"], row["h"], row["l"], row["c"], row["v"], row.get("n"), row.get("vw"), feed,
        )
        for row in records
    ]


DAILY_UPSERT = """
INSERT INTO daily_bars (symbol, trading_date, open, high, low, close, volume, trade_count, vwap, source_feed)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, trading_date) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close,
  volume = EXCLUDED.volume, trade_count = EXCLUDED.trade_count, vwap = EXCLUDED.vwap,
  source_feed = EXCLUDED.source_feed, ingested_at = now()
"""

MINUTE_UPSERT = """
INSERT INTO minute_bars (symbol, ts, open, high, low, close, volume, trade_count, vwap, source_feed)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, ts) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close,
  volume = EXCLUDED.volume, trade_count = EXCLUDED.trade_count, vwap = EXCLUDED.vwap,
  source_feed = EXCLUDED.source_feed, ingested_at = now()
"""


def backfill(days_daily: int = 365, days_minute: int = 30, as_of: date | None = None) -> dict[str, int]:
    as_of = as_of or date.today()
    symbols = load_universe()
    run_id = _run_started("backfill")
    written = 0
    try:
        companies = upsert_companies(symbols)
        daily = list(alpaca.bars(symbols, "1Day", as_of - timedelta(days=days_daily), as_of + timedelta(days=1)))
        minute_end = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=UTC)
        minute = list(alpaca.bars(symbols, "1Min", minute_end - timedelta(days=days_minute), minute_end))
        written = execute_values(DAILY_UPSERT, _daily_rows(daily)) + execute_values(MINUTE_UPSERT, _minute_rows(minute))
        _run_finished(run_id, written)
        return {"companies": companies, "daily_bars": len(daily), "minute_bars": len(minute)}
    except Exception as exc:
        _run_finished(run_id, written, str(exc))
        raise


def nightly(as_of: date | None = None) -> dict[str, int]:
    """Idempotently refresh a padded three-day window to cover weekends/holidays."""
    as_of = as_of or date.today()
    symbols = load_universe()
    run_id = _run_started("nightly")
    written = 0
    try:
        daily = list(alpaca.bars(symbols, "1Day", as_of - timedelta(days=3), as_of + timedelta(days=1)))
        end = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=UTC)
        # Four calendar days reaches back to Friday during a Monday evening run.
        minute = list(alpaca.bars(symbols, "1Min", end - timedelta(days=4), end))
        written = execute_values(DAILY_UPSERT, _daily_rows(daily)) + execute_values(MINUTE_UPSERT, _minute_rows(minute))
        _run_finished(run_id, written)
        LOGGER.info("nightly ingestion wrote %s rows", written)
        return {"daily_bars": len(daily), "minute_bars": len(minute)}
    except Exception as exc:
        _run_finished(run_id, written, str(exc))
        raise
