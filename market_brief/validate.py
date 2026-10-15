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


def allowed_numbers(results: dict[str, list[dict]], as_of: date) -> set[str]:
    allowed = {str(value) for value in (5, 7, 20, 52, 252)}
    for part in (as_of.year, as_of.month, as_of.day):
        allowed.add(_canonical(part) or str(part))
    for item in _walk(results):
        canonical = _canonical(item)
        if canonical is not None:
            allowed.add(canonical)
    return allowed


def validate_numeric_claims(text: str, results: dict[str, list[dict]], as_of: date) -> None:
    """Raise if a numeric token was not returned by a tracked analytical query."""
    allowed = allowed_numbers(results, as_of)
    unsupported = []
    # Dates are checked by the output filename/as-of contract rather than as three independent
    # numeric claims. Removing them also prevents their hyphens being treated as minus signs.
    for match in NUMBER.finditer(ISO_DATE.sub("", text)):
        value = _canonical(match.group())
        if value is not None and value not in allowed:
            unsupported.append(match.group())
    if unsupported:
        raise ValidationError(f"brief has numbers absent from query results: {', '.join(unsupported)}")
