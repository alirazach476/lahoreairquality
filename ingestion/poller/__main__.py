"""Allow ``python -m ingestion.poller`` from the repository root."""

from __future__ import annotations

from lahore_aqi_poller.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
