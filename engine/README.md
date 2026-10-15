# In-memory analytics engine

PostgreSQL remains the durable source of truth. The nightly pipeline materializes bounded tables into a Python columnar engine, runs the seven desk queries there, then passes the results to the same numerical brief validator.

Implemented components:

- `ColumnarTable`: field-aligned Python columns and projection without row-store conversion.
- `BPlusTree`: bulk-loaded, linked-leaf B+ tree on `(symbol, trading_date)` and `(symbol, ts)`.
- Parser/executor: `SELECT`, `WHERE` comparisons joined by `AND`, `ORDER BY`, and `LIMIT`.
- Planner: explains and chooses an index range scan when equality on the leading key and a range on the second key are present; otherwise it performs a full scan.
- Week 4 operators: inner hash join and `count`/`sum`/`avg`/`min`/`max` group-by.

The standard minute hot window is 90 days. Daily history is loaded for 400 calendar days because a true 52-week high/low calculation needs about 252 sessions; this exception is explicit rather than silently changing that query's meaning.

Try the parser and explainable access path:

```python
engine.execute("""
  SELECT symbol, close FROM daily_bars
  WHERE symbol = 'AAPL' AND trading_date >= '2026-01-01'
  ORDER BY trading_date DESC LIMIT 5
""").plan
```

The parser intentionally does not accept joins or aggregations. Those operations are called by the typed engine API used for the sector analytics query; this keeps the educational SQL surface small and its failure mode clear.
