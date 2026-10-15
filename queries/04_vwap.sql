SELECT symbol,
       round((sum(coalesce(vwap, close) * volume) / nullif(sum(volume), 0))::numeric, 2) AS session_vwap,
       round((max(close) - min(close))::numeric, 2) AS intraday_close_range,
       sum(volume) AS minute_volume
FROM minute_bars
WHERE ts >= %(as_of)s::date
  AND ts < (%(as_of)s::date + INTERVAL '1 day')
GROUP BY symbol
HAVING sum(volume) > 0
ORDER BY minute_volume DESC, symbol
LIMIT 10;
