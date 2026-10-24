# scripts/

Developer utility scripts (bootstrap, topic creation, one-off maintenance).

| Script | Purpose |
|--------|---------|
| `run_smoke_test.py` | End-to-end ingestion smoke test (mocked APIs + local stack) |

```bash
python scripts/run_smoke_test.py
# or: make smoke
```

Keep scripts idempotent and documented. Prefer Makefile targets for common workflows.