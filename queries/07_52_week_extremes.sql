WITH windowed AS (
    SELECT symbol, trading_date, close,
           max(close) OVER w AS high_52w,
           min(close) OVER w AS low_52w
    FROM daily_bars
    WHERE trading_date <= %(as_of)s
    WINDOW w AS (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)
)
SELECT symbol, round(close::numeric, 2) AS close, round(high_52w::numeric, 2) AS high_52w,
       round(low_52w::numeric, 2) AS low_52w,
       CASE WHEN close = high_52w THEN '52w_high' WHEN close = low_52w THEN '52w_low' END AS extreme
FROM windowed
WHERE trading_date = %(as_of)s AND (close = high_52w OR close = low_52w)
ORDER BY extreme, symbol;
