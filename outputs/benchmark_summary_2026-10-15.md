# Benchmark results

Generated from the raw samples beside this file.

| System | Case | Median ms | p95 ms |
| --- | --- | ---: | ---: |
| custom_engine | daily_range | 0.253 | 0.271 |
| custom_engine | minute_range | 7.198 | 7.442 |
| custom_engine | sector_group | 17.695 | 117.727 |
| duckdb | daily_range | 0.589 | 0.739 |
| duckdb | minute_range | 0.624 | 0.807 |
| duckdb | sector_group | 2.850 | 6.279 |
| postgres | daily_range | 0.331 | 0.875 |
| postgres | minute_range | 0.548 | 1.368 |
| postgres | sector_group | 16.076 | 16.411 |
