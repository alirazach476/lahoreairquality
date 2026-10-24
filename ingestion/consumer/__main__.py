"""Allow ``python -m ingestion.consumer`` from the repository root."""

from __future__ import annotations

from lahore_aqi_consumer.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
