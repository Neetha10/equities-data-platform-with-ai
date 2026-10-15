WITH prices AS (
    SELECT symbol, trading_date, open, close,
           lag(close) OVER (PARTITION BY symbol ORDER BY trading_date) AS prior_close
    FROM daily_bars
    WHERE trading_date <= %(as_of)s
)
SELECT symbol, round(open::numeric, 2) AS open, round(prior_close::numeric, 2) AS prior_close,
       round((100 * (open / prior_close - 1))::numeric, 2) AS gap_pct
FROM prices
WHERE trading_date = %(as_of)s AND prior_close IS NOT NULL
ORDER BY abs(100 * (open / prior_close - 1)) DESC, symbol
LIMIT 10;
