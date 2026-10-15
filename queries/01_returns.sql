WITH ranked AS (
    SELECT symbol, trading_date, close,
           lag(close) OVER (PARTITION BY symbol ORDER BY trading_date) AS prior_close
    FROM daily_bars
    WHERE trading_date <= %(as_of)s
)
SELECT symbol, round(close::numeric, 2) AS close,
       round((100 * (close / prior_close - 1))::numeric, 2) AS return_pct
FROM ranked
WHERE trading_date = %(as_of)s AND prior_close IS NOT NULL
ORDER BY return_pct DESC, symbol;
