"""Strict parser for the engine's deliberately small SQL subset."""

from __future__ import annotations

import re
from dataclasses import dataclass


class SqlParseError(ValueError):
    pass


@dataclass(frozen=True)
class Condition:
    column: str
    operator: str
    value: str | float | int


@dataclass(frozen=True)
class OrderTerm:
    column: str
    descending: bool = False


@dataclass(frozen=True)
class SelectQuery:
    columns: tuple[str, ...]
    table: str
    conditions: tuple[Condition, ...] = ()
    order_by: tuple[OrderTerm, ...] = ()
    limit: int | None = None


TOKEN = re.compile(r"\s*(>=|<=|!=|=|>|<|,|\*|\(|\)|'(?:[^']|'')*'|[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?)")
KEYWORDS = {"SELECT", "FROM", "WHERE", "AND", "ORDER", "BY", "ASC", "DESC", "LIMIT"}


def _tokens(sql: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(sql):
        match = TOKEN.match(sql, position)
        if not match:
            if sql[position:].strip() == ";":
                break
            raise SqlParseError(f"unsupported SQL near {sql[position:position + 20]!r}")
        tokens.append(match.group(1))
        position = match.end()
    return tokens


def _literal(token: str) -> str | float | int:
    if token.startswith("'"):
        return token[1:-1].replace("''", "'")
    if "." in token:
        return float(token)
    if token.lstrip("-").isdigit():
        return int(token)
    raise SqlParseError(f"expected a literal, got {token!r}")


def parse(sql: str) -> SelectQuery:
    tokens = _tokens(sql.strip())
    position = 0

    def take(expected: str | None = None) -> str:
        nonlocal position
        if position >= len(tokens):
            raise SqlParseError(f"expected {expected or 'token'}, got end of input")
        token = tokens[position]
        position += 1
        if expected and token.upper() != expected:
            raise SqlParseError(f"expected {expected}, got {token}")
        return token

    take("SELECT")
    columns = [take()]
    while position < len(tokens) and tokens[position] == ",":
        take(",")
        columns.append(take())
    take("FROM")
    table = take()
    conditions: list[Condition] = []
    order_by: list[OrderTerm] = []
    limit: int | None = None
    if position < len(tokens) and tokens[position].upper() == "WHERE":
        take("WHERE")
        while True:
            column, operator, value = take(), take(), _literal(take())
            if operator not in {"=", "!=", ">", ">=", "<", "<="}:
                raise SqlParseError(f"unsupported comparison {operator}")
            conditions.append(Condition(column, operator, value))
            if position >= len(tokens) or tokens[position].upper() != "AND":
                break
            take("AND")
    if position < len(tokens) and tokens[position].upper() == "ORDER":
        take("ORDER")
        take("BY")
        while True:
            column = take()
            descending = position < len(tokens) and tokens[position].upper() == "DESC"
            if position < len(tokens) and tokens[position].upper() in {"ASC", "DESC"}:
                take()
            order_by.append(OrderTerm(column, descending))
            if position >= len(tokens) or tokens[position] != ",":
                break
            take(",")
    if position < len(tokens) and tokens[position].upper() == "LIMIT":
        take("LIMIT")
        limit_token = take()
        if not limit_token.isdigit():
            raise SqlParseError("LIMIT must be a non-negative integer")
        limit = int(limit_token)
    if position != len(tokens):
        raise SqlParseError(f"unexpected token {tokens[position]!r}")
    if not columns or any(column.upper() in KEYWORDS for column in columns):
        raise SqlParseError("invalid select list")
    return SelectQuery(tuple(columns), table, tuple(conditions), tuple(order_by), limit)
