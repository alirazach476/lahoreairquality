"""CLI helper: print how to launch the local Dagster UI."""

from __future__ import annotations


def main() -> int:
    print(
        "Lahore AQI Dagster\n"
        "\n"
        "  cd orchestration/dagster\n"
        "  set DAGSTER_HOME to this directory (or use make dagster-dev)\n"
        "  dagster dev -w workspace.yaml\n"
        "\n"
        "Secrets come from the repo-root .env / environment variables.\n"
        "Schedules/sensors start STOPPED — enable them in the UI when ready.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
