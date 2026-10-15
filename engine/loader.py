"""Materialize a bounded PostgreSQL window into the in-memory engine."""

from __future__ import annotations

from datetime import date, timedelta

from market_brief.db import query

from .core import ColumnarTable, Engine


def load_hot_window(
    as_of: date,
    *,
    daily_window_days: int = 400,
    minute_window_days: int = 90,
) -> Engine:
    """Load engine tables and B+ tree indexes from PostgreSQL's durable source of truth.

    The daily window is deliberately longer than the normal 30–90 day hot minute window because
    the 52-week-extremes brief query needs 252 sessions of price history.
    """
    engine = Engine()
    daily = query(
        """SELECT symbol, trading_date, open, high, low, close, volume, trade_count, vwap
           FROM daily_bars
           WHERE trading_date >= %s AND trading_date <= %s""",
        (as_of - timedelta(days=daily_window_days), as_of),
    )
    minute = query(
        """SELECT symbol, ts, open, high, low, close, volume, trade_count, vwap
           FROM minute_bars
           WHERE ts >= %s::date AND ts < (%s::date + INTERVAL '1 day')""",
        (as_of - timedelta(days=minute_window_days), as_of),
    )
    companies = query("SELECT symbol, sector FROM companies")
    daily_table = ColumnarTable.from_rows("daily_bars", daily)
    minute_table = ColumnarTable.from_rows("minute_bars", minute)
    companies_table = ColumnarTable.from_rows("companies", companies)
    daily_table.create_btree_index("symbol", "trading_date")
    minute_table.create_btree_index("symbol", "ts")
    engine.register(daily_table)
    engine.register(minute_table)
    engine.register(companies_table)
    return engine
