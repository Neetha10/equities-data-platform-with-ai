"""Small, retrying client for Alpaca's historical stock-bars endpoint."""

from collections.abc import Iterator
from datetime import date, datetime

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import settings

BASE_URL = "https://data.alpaca.markets/v2/stocks/bars"


class AlpacaError(RuntimeError):
    pass


@retry(
    retry=retry_if_exception_type((requests.RequestException, AlpacaError)),
    wait=wait_exponential(min=1, max=20),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _get(params: dict[str, str]) -> dict:
    cfg = settings()
    if not cfg.alpaca_api_key or not cfg.alpaca_api_secret:
        raise AlpacaError("ALPACA_API_KEY and ALPACA_API_SECRET must be set")
    response = requests.get(
        BASE_URL,
        params=params,
        headers={
            "APCA-API-KEY-ID": cfg.alpaca_api_key,
            "APCA-API-SECRET-KEY": cfg.alpaca_api_secret,
        },
        timeout=30,
    )
    if response.status_code in {429, 500, 502, 503, 504}:
        raise AlpacaError(f"retryable Alpaca response {response.status_code}: {response.text[:300]}")
    response.raise_for_status()
    return response.json()


def bars(symbols: list[str], timeframe: str, start: date | datetime, end: date | datetime) -> Iterator[dict]:
    """Yield API bars, transparently following Alpaca's page token."""
    if not symbols:
        return
    params = {
        "symbols": ",".join(symbols),
        "timeframe": timeframe,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "adjustment": "all",
        "feed": settings().alpaca_feed,
        "limit": "10000",
    }
    while True:
        payload = _get(params)
        for symbol, records in payload.get("bars", {}).items():
            for record in records:
                yield {"symbol": symbol, **record}
        token = payload.get("next_page_token")
        if not token:
            break
        params["page_token"] = token
