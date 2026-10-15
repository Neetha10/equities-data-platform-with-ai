WITH volumes AS (
    SELECT symbol, trading_date, volume,
           avg(volume) OVER (
             PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
           ) AS avg_20d_volume
    FROM daily_bars
    WHERE trading_date <= %(as_of)s
)
SELECT symbol, volume, round(avg_20d_volume::numeric, 0) AS avg_20d_volume,
       round((volume / nullif(avg_20d_volume, 0))::numeric, 2) AS volume_multiple
FROM volumes
WHERE trading_date = %(as_of)s AND avg_20d_volume IS NOT NULL
ORDER BY volume_multiple DESC, symbol
LIMIT 10;
