# Benchmark results

Generated from the raw samples beside this file.

| System | Case | Median ms | p95 ms |
| --- | --- | ---: | ---: |
| custom_engine | daily_range | 0.245 | 0.299 |
| custom_engine | minute_range | 7.241 | 8.827 |
| custom_engine | sector_group | 17.273 | 132.573 |
| duckdb | daily_range | 33.880 | 34.615 |
| duckdb | minute_range | 769.613 | 832.348 |
| duckdb | sector_group | 36.518 | 40.802 |
| postgres | daily_range | 6.142 | 9.889 |
| postgres | minute_range | 6.582 | 11.844 |
| postgres | sector_group | 13.434 | 18.970 |
