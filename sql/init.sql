CREATE TABLE IF NOT EXISTS companies (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cik TEXT,
    sic TEXT,
    sector TEXT NOT NULL DEFAULT 'Unknown',
    industry TEXT,
    exchange TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_bars (
    symbol TEXT NOT NULL REFERENCES companies(symbol),
    trading_date DATE NOT NULL,
    open NUMERIC(18, 6) NOT NULL,
    high NUMERIC(18, 6) NOT NULL,
    low NUMERIC(18, 6) NOT NULL,
    close NUMERIC(18, 6) NOT NULL,
    volume BIGINT NOT NULL,
    trade_count BIGINT,
    vwap NUMERIC(18, 6),
    source_feed TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, trading_date),
    CHECK (high >= low),
    CHECK (volume >= 0)
);
CREATE INDEX IF NOT EXISTS daily_bars_date_idx ON daily_bars (trading_date);

CREATE TABLE IF NOT EXISTS minute_bars (
    symbol TEXT NOT NULL REFERENCES companies(symbol),
    ts TIMESTAMPTZ NOT NULL,
    open NUMERIC(18, 6) NOT NULL,
    high NUMERIC(18, 6) NOT NULL,
    low NUMERIC(18, 6) NOT NULL,
    close NUMERIC(18, 6) NOT NULL,
    volume BIGINT NOT NULL,
    trade_count BIGINT,
    vwap NUMERIC(18, 6),
    source_feed TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, ts),
    CHECK (high >= low),
    CHECK (volume >= 0)
);
CREATE INDEX IF NOT EXISTS minute_bars_symbol_ts_idx ON minute_bars (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS minute_bars_ts_idx ON minute_bars (ts);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id BIGSERIAL PRIMARY KEY,
    run_type TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    rows_written BIGINT NOT NULL DEFAULT 0,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
