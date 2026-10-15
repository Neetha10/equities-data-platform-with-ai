"""Reference-data loader using the SEC company tickers endpoint."""

import time
from collections.abc import Iterable

import requests

from .config import settings
from .db import execute_values

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def sec_sector(sic: str | None) -> str:
    """Coarse, reproducible sector label from an EDGAR SIC code—not a GICS classification."""
    if not sic or not sic.isdigit():
        return "Unknown"
    code = int(sic)
    for lower, upper, label in [
        (100, 999, "Agriculture"), (1000, 1499, "Energy & Mining"), (1500, 1799, "Construction"),
        (2000, 3999, "Manufacturing"), (4000, 4999, "Transportation & Utilities"),
        (5000, 5199, "Wholesale Trade"), (5200, 5999, "Retail Trade"),
        (6000, 6799, "Financial Services"), (7000, 8999, "Services"), (9100, 9999, "Public Administration"),
    ]:
        if lower <= code <= upper:
            return label
    return "Other"


def fetch_company_profile(cik: str) -> tuple[str | None, str | None]:
    """Read SEC's issuer SIC metadata, paced below its published request-rate guidance."""
    response = requests.get(
        SUBMISSIONS_URL.format(cik=cik),
        headers={"User-Agent": settings().sec_user_agent, "Accept-Encoding": "gzip, deflate"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    sic = str(payload["sic"]) if payload.get("sic") is not None else None
    return sic, payload.get("sicDescription")


def fetch_company_reference() -> dict[str, tuple[str, str, str]]:
    """Return ticker -> (name, zero-padded CIK, exchange)."""
    response = requests.get(
        TICKERS_URL,
        headers={"User-Agent": settings().sec_user_agent, "Accept-Encoding": "gzip, deflate"},
        timeout=30,
    )
    response.raise_for_status()
    fields = response.json().get("fields", [])
    rows = response.json().get("data", [])
    index = {name: position for position, name in enumerate(fields)}
    return {
        str(row[index["ticker"]]).upper(): (
            str(row[index["name"]]),
            str(row[index["cik"]]).zfill(10),
            str(row[index.get("exchange", 0)]),
        )
        for row in rows
    }


def upsert_companies(symbols: Iterable[str]) -> int:
    reference = fetch_company_reference()
    rows = []
    for symbol in symbols:
        # The SEC lists some share classes without punctuation; preserve the trading symbol.
        item = reference.get(symbol) or reference.get(symbol.replace(".", "-"))
        if item:
            name, cik, exchange = item
            sic, industry = fetch_company_profile(cik)
            sector = sec_sector(sic)
            # The SEC asks automated callers to stay at or below 10 requests/second.
            time.sleep(0.11)
        else:
            name, cik, exchange, sic, industry, sector = symbol, None, None, None, None, "Unknown"
        rows.append((symbol, name, cik, sic, sector, industry, exchange))
    written = execute_values(
        """
        INSERT INTO companies (symbol, name, cik, sic, sector, industry, exchange)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol) DO UPDATE SET
            name = EXCLUDED.name, cik = EXCLUDED.cik, sic = EXCLUDED.sic, sector = EXCLUDED.sector,
            industry = EXCLUDED.industry, exchange = EXCLUDED.exchange,
            updated_at = now()
        """,
        rows,
    )
    return written
