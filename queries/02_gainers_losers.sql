WITH returns AS (
    SELECT symbol, close,
           100 * (close / lag(close) OVER (PARTITION BY symbol ORDER BY trading_date) - 1) AS return_pct,
           trading_date
    FROM daily_bars
    WHERE trading_date <= %(as_of)s
), ranked AS (
    SELECT *, row_number() OVER (ORDER BY return_pct DESC) AS gainer_rank,
              row_number() OVER (ORDER BY return_pct ASC) AS loser_rank
    FROM returns WHERE trading_date = %(as_of)s AND return_pct IS NOT NULL
)
SELECT CASE WHEN gainer_rank <= 5 THEN 'gainer' ELSE 'loser' END AS direction,
       symbol, round(close::numeric, 2) AS close, round(return_pct::numeric, 2) AS return_pct
FROM ranked
WHERE gainer_rank <= 5 OR loser_rank <= 5
ORDER BY direction, return_pct DESC;
