#!/usr/bin/env python3
"""Run the end-to-end local ingestion smoke test.

Flow under test (external APIs mocked):

    OpenAQ / Open-Meteo clients → poller → Redpanda → consumer → PostgreSQL + MinIO

Usage (from repo root):

    python scripts/run_smoke_test.py
    # or: make smoke

Starts Compose infrastructure when Docker is available, then runs ``pytest -m smoke``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INFRA_SERVICES = (
    "postgres",
    "minio",
    "minio-init",
    "redpanda",
    "redpanda-init-topics",
    "migrate",
)


def _ensure_env_file() -> None:
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"
    if env_path.exists():
        return
    if not example.exists():
        print("Missing .env and .env.example — cannot run smoke test.", file=sys.stderr)
        raise SystemExit(2)
    shutil.copy(example, env_path)
    print("Created .env from .env.example")


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _compose(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def _start_infrastructure() -> None:
    if not _docker_available():
        print(
            "Docker not available — assuming Postgres/MinIO/Redpanda are already "
            "reachable via .env host settings."
        )
        return

    print("Starting Compose infrastructure (postgres, minio, redpanda, migrate)…")
    up = _compose("up", "-d", "--build", *INFRA_SERVICES)
    if up.returncode != 0:
        print(up.stdout)
        print(up.stderr, file=sys.stderr)
        raise SystemExit(up.returncode)

    # Avoid racing the long-running Compose poller/consumer on shared brokers.
    _compose("stop", "poller", "consumer")

    print("Waiting for Postgres health…")
    for _ in range(60):
        _compose("ps", "--status", "running", "postgres")
        health = _compose("exec", "-T", "postgres", "pg_isready")
        if health.returncode == 0:
            break
        time.sleep(2)
    else:
        print("Postgres did not become ready in time.", file=sys.stderr)
        raise SystemExit(1)

    # Give Redpanda / MinIO a moment after compose reports started.
    time.sleep(3)
    print("Infrastructure is up.")


def main() -> int:
    os.chdir(ROOT)
    _ensure_env_file()
    _start_infrastructure()

    env = os.environ.copy()
    env["RUN_SMOKE_TESTS"] = "1"
    # Prefer host-side localhost endpoints from .env for the in-process smoke client.
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "smoke",
        "-v",
        "tests/smoke",
        "--tb=short",
    ]
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
