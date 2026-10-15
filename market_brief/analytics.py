"""Run the immutable, reviewable query set that supplies the daily brief."""

from datetime import date
from pathlib import Path

from .config import settings
from .db import connection, read_sql

QUERY_DIR = Path("queries")


def available_queries() -> list[Path]:
    return sorted(QUERY_DIR.glob("*.sql"))


def run_queries(as_of: date, backend: str | None = None) -> dict[str, list[dict]]:
    selected_backend = backend or settings().analytics_backend
    if selected_backend == "engine":
        from engine.desk import run_desk_queries
        from engine.loader import load_hot_window

        return run_desk_queries(load_hot_window(as_of), as_of)
    if selected_backend != "postgres":
        raise ValueError("analytics_backend must be 'engine' or 'postgres'")
    results: dict[str, list[dict]] = {}
    with connection() as conn, conn.cursor() as cur:
        for path in available_queries():
            cur.execute(read_sql(path), {"as_of": as_of})
            results[path.stem] = list(cur.fetchall())
    return results
