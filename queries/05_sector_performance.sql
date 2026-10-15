WITH returns AS (
    SELECT d.symbol, d.trading_date,
           100 * (d.close / lag(d.close) OVER (PARTITION BY d.symbol ORDER BY d.trading_date) - 1) AS return_pct
    FROM daily_bars d
    WHERE d.trading_date <= %(as_of)s
)
SELECT c.sector, count(*) AS constituents,
       round(avg(r.return_pct)::numeric, 2) AS equal_weight_return_pct
FROM returns r
JOIN companies c USING (symbol)
WHERE r.trading_date = %(as_of)s AND r.return_pct IS NOT NULL
GROUP BY c.sector
ORDER BY equal_weight_return_pct DESC, sector;
