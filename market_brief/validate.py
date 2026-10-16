"""Guardrail: generated prose may only contain values present in the fact ledger."""

import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

NUMBER = re.compile(r"(?<![A-Za-z_])-?\$?\d[\d,]*(?:\.\d+)?(?=%|x\b|\b)")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


class ValidationError(ValueError):
    pass


def _canonical(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (date, datetime)):
        return None
    try:
        return format(Decimal(str(value).replace(",", "").replace("$", "")).normalize(), "f")
    except (InvalidOperation, ValueError):
        return None


def _walk(values: object) -> Iterable[object]:
    if isinstance(values, dict):
        for value in values.values():
            yield from _walk(value)
    elif isinstance(values, list):
        for value in values:
            yield from _walk(value)
    else:
        yield values


def _absolute_number(value: object) -> str | None:
    canonical = _canonical(value)
    return format(abs(Decimal(canonical)).normalize(), "f") if canonical is not None else None


def allowed_numbers(results: dict[str, list[dict]], as_of: date) -> set[str]:
    """Numbers supported by non-symbol result rows; dates and query constants are never allowed."""
    allowed: set[str] = set()
    for rows in results.values():
        for row in rows:
            if "symbol" in row:
                continue
            for value in _walk(row):
                canonical = _absolute_number(value)
                if canonical is not None:
                    allowed.add(canonical)
    return allowed


def _numbers_by_symbol(results: dict[str, list[dict]]) -> dict[str, set[str]]:
    supported: dict[str, set[str]] = {}
    for rows in results.values():
        for item in rows:
            if not isinstance(item.get("symbol"), str):
                continue
            symbol = item["symbol"]
            supported.setdefault(symbol, set())
            for value in _walk(item):
                canonical = _absolute_number(value)
                if canonical is not None:
                    supported[symbol].add(canonical)
    return supported


def _sentence(text: str, position: int) -> tuple[int, str]:
    start = max(text.rfind(marker, 0, position) for marker in ("\n", ".", "!", "?")) + 1
    ends = [text.find(marker, position) for marker in ("\n", ".", "!", "?")]
    end = min(end for end in ends if end >= 0) if any(end >= 0 for end in ends) else len(text)
    return start, text[start:end]


def _nearest_symbol(sentence: str, absolute_position: int, symbols: set[str], sentence_start: int) -> str | None:
    candidates: list[tuple[int, str]] = []
    for match in re.finditer(r"\b[A-Z][A-Z.\-]{0,9}\b", sentence):
        symbol = match.group()
        if symbol in symbols:
            distance = abs((sentence_start + match.start()) - absolute_position)
            candidates.append((distance, symbol))
    return min(candidates)[1] if candidates else None


def validate_numeric_claims(text: str, results: dict[str, list[dict]], as_of: date) -> None:
    """Raise if a numeric token was not returned by a tracked analytical query."""
    allowed = allowed_numbers(results, as_of)
    by_symbol = _numbers_by_symbol(results)
    unsupported = []
    # Dates are checked by the output filename/as-of contract rather than as three independent
    # numeric claims. Removing them also prevents their hyphens being treated as minus signs.
    without_dates = ISO_DATE.sub(lambda match: " " * len(match.group()), text)
    for match in NUMBER.finditer(without_dates):
        value = _absolute_number(match.group())
        sentence_start, sentence = _sentence(text, match.start())
        symbol = _nearest_symbol(sentence, match.start(), set(by_symbol), sentence_start)
        valid_values = by_symbol[symbol] if symbol is not None else allowed
        if value is not None and value not in valid_values:
            unsupported.append(match.group())
    if unsupported:
        raise ValidationError(f"brief has numbers absent from query results: {', '.join(unsupported)}")
