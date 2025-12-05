# Test Suite Runner

Use `run_test_suite.py` to execute the NL→FOL regression suite defined in `test.json`.

```bash
python tests\run_test_suite.py ^
	--input tests\test.json ^
	--output tests\test_results.json ^
	--log-file tests\test_results.log
```

- `--stop-on-failure` halts as soon as a test fails.
- Results are stored as structured JSON (`test_results.json`) plus a human-readable log (`test_results.log`) in the same folder by default.
- `--max-tests N` limits execution to the first `N` scenarios (defaults to 343 to keep runs manageable; pass `0` to run the full suite).
- `--graph-output PATH` saves a PNG dashboard summarizing pass/fail counts, errors, query accuracy, and timing. A second timeline figure is also emitted automatically using the same stem plus `_progress`.
- `--progress-graph PATH` overrides the timeline output location, while `--skip-graphs` disables plotting entirely (useful on servers without display back-ends).
