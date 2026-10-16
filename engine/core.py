"""Column-at-a-time execution, B+ tree access paths, hash joins, and group-by."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from math import ceil, log2
from typing import Literal

from .index import BPlusTree
from .parser import Condition, SelectQuery, parse

Scalar = str | int | float | Decimal | date | datetime | None


@dataclass(frozen=True)
class Plan:
    strategy: Literal["full_scan", "index_range_scan"]
    estimated_rows: int
    reason: str


@dataclass(frozen=True)
class QueryResult:
    rows: list[dict[str, Scalar]]
    plan: Plan


class ColumnarTable:
    def __init__(self, name: str, rows: Iterable[dict[str, Scalar]]):
        materialized = list(rows)
        self.name = name
        names = {column for row in materialized for column in row}
        self.columns = {column: [row.get(column) for row in materialized] for column in names}
        self.row_count = len(materialized)
        self.indexes: dict[tuple[str, ...], BPlusTree[tuple, int]] = {}
        self.index_bounds: dict[tuple[str, ...], tuple[Scalar, Scalar]] = {}
        self.grouped_positions: dict[str, dict[Scalar, tuple[int, ...]]] = {}
        self.cache: dict[str, object] = {}

    @classmethod
    def from_rows(cls, name: str, rows: Iterable[dict[str, Scalar]]) -> ColumnarTable:
        return cls(name, rows)

    def create_btree_index(self, *columns: str) -> None:
        if not columns or any(column not in self.columns for column in columns):
            raise ValueError(f"cannot index missing columns: {columns}")
        items = [
            (tuple(self.columns[column][row_id] for column in columns), row_id)
            for row_id in range(self.row_count)
        ]
        index_columns = tuple(columns)
        self.indexes[index_columns] = BPlusTree(items)
        values = [value for value in self.columns[columns[-1]] if value is not None]
        if values:
            self.index_bounds[index_columns] = (min(values), max(values))

    def create_grouped_positions(self, column: str) -> None:
        if column not in self.columns:
            raise ValueError(f"cannot group missing column: {column}")
        groups: dict[Scalar, list[int]] = defaultdict(list)
        for row_id, value in enumerate(self.columns[column]):
            groups[value].append(row_id)
        self.grouped_positions[column] = {value: tuple(row_ids) for value, row_ids in groups.items()}

    def row(self, row_id: int) -> dict[str, Scalar]:
        return {column: values[row_id] for column, values in self.columns.items()}

    def project(self, row_id: int, columns: tuple[str, ...]) -> dict[str, Scalar]:
        if columns == ("*",):
            return self.row(row_id)
        return {column: self.columns[column][row_id] for column in columns}


def _coerce(value: Scalar, target: Scalar) -> Scalar:
    if value is None or target is None:
        return value
    if isinstance(target, datetime) and isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None and target.tzinfo is not None:
            return parsed.replace(tzinfo=target.tzinfo)
        return parsed
    if isinstance(target, date) and not isinstance(target, datetime) and isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(target, Decimal) and not isinstance(value, Decimal):
        return Decimal(str(value))
    if isinstance(target, int) and not isinstance(target, bool):
        return int(value)
    if isinstance(target, float):
        return float(value)
    return value


def _matches(actual: Scalar, operator: str, expected: Scalar) -> bool:
    if actual is None:
        return operator == "!=" and expected is not None
    return {
        "=": actual == expected,
        "!=": actual != expected,
        ">": actual > expected,
        ">=": actual >= expected,
        "<": actual < expected,
        "<=": actual <= expected,
    }[operator]


class Engine:
    def __init__(self):
        self.tables: dict[str, ColumnarTable] = {}

    def register(self, table: ColumnarTable) -> None:
        self.tables[table.name] = table

    def explain(self, query: SelectQuery) -> Plan:
        table = self.tables[query.table]
        for index_columns, index in table.indexes.items():
            first, *rest = index_columns
            equality = next((c for c in query.conditions if c.column == first and c.operator == "="), None)
            if not equality or not rest:
                continue
            second = rest[0]
            bounds = [c for c in query.conditions if c.column == second and c.operator in {">", ">=", "<", "<="}]
            if bounds:
                estimate = max(1, min(index.size, ceil(index.size * 0.05)))
                index_cost = ceil(log2(max(2, index.size))) + estimate
                if index_cost < table.row_count:
                    return Plan(
                        "index_range_scan",
                        estimate,
                        f"{index_columns} estimated cost {index_cost} is below full scan cost {table.row_count}",
                    )
                return Plan(
                    "full_scan",
                    table.row_count,
                    f"index cost {index_cost} is not lower than full scan cost {table.row_count}",
                )
        return Plan("full_scan", table.row_count, "no composite index satisfies the predicates")

    def _candidate_ids(
        self,
        table: ColumnarTable,
        query: SelectQuery,
        plan: Plan,
        prepared: dict[Condition, Scalar],
    ) -> list[int]:
        if plan.strategy == "full_scan":
            return list(range(table.row_count))
        for columns, index in table.indexes.items():
            first, second = columns[:2]
            equality = next(c for c in query.conditions if c.column == first and c.operator == "=")
            first_value = prepared[equality]
            lower: Scalar | None = None
            upper: Scalar | None = None
            for condition in query.conditions:
                if condition.column != second:
                    continue
                value = prepared[condition]
                if condition.operator in {">", ">="}:
                    lower = value if lower is None else max(lower, value)
                if condition.operator in {"<", "<="}:
                    upper = value if upper is None else min(upper, value)
            minimum, maximum = table.index_bounds[columns]
            low_key = (first_value, lower if lower is not None else minimum)
            high_key = (first_value, upper if upper is not None else maximum)
            return index.range(low_key, high_key)
        return list(range(table.row_count))

    def execute(self, sql_or_query: str | SelectQuery) -> QueryResult:
        query = parse(sql_or_query) if isinstance(sql_or_query, str) else sql_or_query
        if query.table not in self.tables:
            raise KeyError(f"unknown table {query.table!r}")
        table = self.tables[query.table]
        if query.columns != ("*",):
            unknown = set(query.columns) - set(table.columns)
            if unknown:
                raise KeyError(f"unknown projected columns: {sorted(unknown)}")
        for condition in query.conditions:
            if condition.column not in table.columns:
                raise KeyError(f"unknown filter column: {condition.column}")
        plan = self.explain(query)
        prepared: dict[Condition, Scalar] = {}
        for condition in query.conditions:
            prototype = next((value for value in table.columns[condition.column] if value is not None), None)
            prepared[condition] = _coerce(condition.value, prototype)
        row_ids = [
            row_id
            for row_id in self._candidate_ids(table, query, plan, prepared)
            if all(
                _matches(table.columns[condition.column][row_id], condition.operator, prepared[condition])
                for condition in query.conditions
            )
        ]
        # Sort before projection so ORDER BY need not appear in SELECT.
        for term in reversed(query.order_by):
            row_ids.sort(key=lambda row_id: table.columns[term.column][row_id], reverse=term.descending)
        if query.limit is not None:
            row_ids = row_ids[: query.limit]
        return QueryResult([table.project(row_id, query.columns) for row_id in row_ids], plan)

    def hash_join(
        self,
        left: str,
        right: str,
        left_key: str,
        right_key: str,
        select: tuple[tuple[str, str], ...] | None = None,
    ) -> ColumnarTable:
        """Inner hash join. `select` maps output name -> `left.col` or `right.col`."""
        left_table, right_table = self.tables[left], self.tables[right]
        if left_key not in left_table.columns or right_key not in right_table.columns:
            raise KeyError("join key does not exist")
        buckets: dict[Scalar, list[int]] = defaultdict(list)
        for row_id, value in enumerate(right_table.columns[right_key]):
            buckets[value].append(row_id)
        select = select or tuple(
            [(f"left_{column}", f"left.{column}") for column in left_table.columns]
            + [(f"right_{column}", f"right.{column}") for column in right_table.columns]
        )
        rows: list[dict[str, Scalar]] = []
        for left_id, key in enumerate(left_table.columns[left_key]):
            for right_id in buckets.get(key, []):
                row: dict[str, Scalar] = {}
                for output, reference in select:
                    side, column = reference.split(".", 1)
                    row[output] = (left_table if side == "left" else right_table).columns[column][left_id if side == "left" else right_id]
                rows.append(row)
        return ColumnarTable.from_rows(f"{left}_join_{right}", rows)

    @staticmethod
    def group_by(
        table: ColumnarTable,
        keys: tuple[str, ...],
        aggregates: dict[str, tuple[Literal["count", "sum", "avg", "min", "max"], str | None]],
    ) -> list[dict[str, Scalar]]:
        buckets: dict[tuple[Scalar, ...], list[int]] = defaultdict(list)
        for row_id in range(table.row_count):
            buckets[tuple(table.columns[key][row_id] for key in keys)].append(row_id)
        output: list[dict[str, Scalar]] = []
        for group, ids in buckets.items():
            row = dict(zip(keys, group))
            for alias, (function, column) in aggregates.items():
                values = [table.columns[column][row_id] for row_id in ids] if column else []
                numeric = [value for value in values if value is not None]
                row[alias] = {
                    "count": len(ids),
                    "sum": sum(numeric),
                    "avg": sum(numeric) / len(numeric) if numeric else None,
                    "min": min(numeric) if numeric else None,
                    "max": max(numeric) if numeric else None,
                }[function]
            output.append(row)
        return output
