"""Reference-data loader using the SEC company tickers endpoint."""

import time
from collections.abc import Iterable

import requests

from .config import settings
from .db import execute_values

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


SECTOR_OVERRIDES = {
    "AAPL": "Information Technology", "MSFT": "Information Technology", "NVDA": "Information Technology",
    "AVGO": "Information Technology", "AMD": "Information Technology", "GOOGL": "Communication Services",
    "GOOG": "Communication Services", "META": "Communication Services", "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary", "XOM": "Energy", "CVX": "Energy", "LLY": "Health Care",
    "UNH": "Health Care", "JPM": "Financials", "BAC": "Financials",
}


def sec_sector(sic: str | None, symbol: str | None = None) -> str:
    """GICS-style, reproducible labels from EDGAR SIC codes with liquid-universe overrides."""
    if symbol and symbol in SECTOR_OVERRIDES:
        return SECTOR_OVERRIDES[symbol]
    if not sic or not sic.isdigit():
        return "Unknown"
    code = int(sic)
    for lower, upper, label in [
        (100, 999, "Materials"), (1000, 1499, "Energy"), (1500, 1799, "Industrials"),
        (2000, 2099, "Consumer Staples"), (2100, 2799, "Materials"), (2800, 2829, "Materials"),
        (2830, 2839, "Health Care"), (2840, 2999, "Materials"), (3000, 3569, "Industrials"),
        (3570, 3599, "Information Technology"), (3600, 3669, "Industrials"),
        (3670, 3679, "Information Technology"), (3680, 3799, "Industrials"),
        (3800, 3869, "Health Care"), (3870, 3999, "Industrials"), (4000, 4799, "Industrials"),
        (4800, 4899, "Communication Services"), (4900, 4999, "Utilities"),
        (5000, 5199, "Industrials"), (5200, 5999, "Consumer Discretionary"),
        (6000, 6499, "Financials"), (6500, 6799, "Real Estate"), (7000, 7999, "Consumer Discretionary"),
        (8000, 8999, "Health Care"), (9100, 9999, "Public Administration"),
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
            sector = sec_sector(sic, symbol)
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
