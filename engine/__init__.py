"""Educational in-memory columnar query engine used for Phase 2 analytics."""

from .core import ColumnarTable, Engine, QueryResult
from .parser import SqlParseError, parse

__all__ = ["ColumnarTable", "Engine", "QueryResult", "SqlParseError", "parse"]
