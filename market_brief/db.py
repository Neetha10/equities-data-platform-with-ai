from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .config import settings


@contextmanager
def connection():
    with psycopg.connect(settings().database_url, row_factory=dict_row) as conn:
        yield conn


def read_sql(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def query(sql: str, params: Sequence[object] = ()) -> list[dict]:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def execute_values(sql: str, rows: Iterable[Sequence[object]]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    with connection() as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)
        return len(rows)
