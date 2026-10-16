# Benchmark results

Generated from the raw samples beside this file.

| System | Case | Median ms | p95 ms |
| --- | --- | ---: | ---: |
| custom_engine | daily_range | 0.041 | 0.047 |
| custom_engine | minute_range | 0.868 | 0.945 |
| custom_engine | sector_group | 1.298 | 1.432 |
| duckdb | daily_range | 0.504 | 0.669 |
| duckdb | minute_range | 0.734 | 1.004 |
| duckdb | sector_group | 2.042 | 2.685 |
| postgres | daily_range | 0.240 | 4.633 |
| postgres | minute_range | 0.534 | 6.894 |
| postgres | sector_group | 17.001 | 18.349 |

## Setup costs (excluded from timed queries)

- daily_rows_by_symbol_ms: 21.416 ms
