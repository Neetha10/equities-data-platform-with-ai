# Benchmark results

Generated from the raw samples beside this file.

| System | Case | Median ms | p95 ms |
| --- | --- | ---: | ---: |
| custom_engine | daily_range | 0.041 | 0.045 |
| custom_engine | minute_range | 0.492 | 0.508 |
| custom_engine | sector_group | 1.287 | 1.366 |
| duckdb | daily_range | 0.507 | 0.638 |
| duckdb | minute_range | 0.758 | 0.821 |
| duckdb | sector_group | 1.928 | 3.237 |
| postgres | daily_range | 0.206 | 0.291 |
| postgres | minute_range | 0.432 | 0.517 |
| postgres | sector_group | 16.386 | 16.935 |
