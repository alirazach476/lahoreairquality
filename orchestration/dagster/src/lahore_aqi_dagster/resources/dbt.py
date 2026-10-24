"""dbt CLI resource — invokes local dbt; secrets via env Postgres vars."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dagster import ConfigurableResource

from lahore_aqi_dagster.failures import transformation_failure


@dataclass(frozen=True, slots=True)
class DbtRunResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class DbtResource(ConfigurableResource):
    """Runs ``dbt`` subprocesses against the project under ``dbt/lahore_air_quality``."""

    project_dir: str = ""
    profiles_dir: str = ""
    skip_if_unavailable: bool = True

    def _project_dir(self) -> Path:
        if self.project_dir.strip():
            return Path(self.project_dir).expanduser().resolve()
        env = os.environ.get("DBT_PROJECT_DIR")
        if env:
            return Path(env).expanduser().resolve()
        # resources/dbt.py → repo root
        return (Path(__file__).resolve().parents[5] / "dbt" / "lahore_air_quality").resolve()

    def _profiles_dir(self) -> Path:
        if self.profiles_dir.strip():
            return Path(self.profiles_dir).expanduser().resolve()
        env = os.environ.get("DBT_PROFILES_DIR")
        if env:
            return Path(env).expanduser().resolve()
        return self._project_dir()

    def available(self) -> bool:
        return shutil.which("dbt") is not None and self._project_dir().is_dir()

    def execute(
        self,
        args: Sequence[str],
        *,
        stage: str,
        raise_on_error: bool = True,
    ) -> DbtRunResult:
        project = self._project_dir()
        profiles = self._profiles_dir()
        if not self.available():
            if self.skip_if_unavailable:
                return DbtRunResult(
                    command=("dbt", *tuple(args)),
                    returncode=0,
                    stdout="dbt skipped: CLI or project directory unavailable",
                    stderr="",
                    skipped=True,
                )
            transformation_failure(
                "dbt CLI or project directory is unavailable",
                stage=stage,
                project_dir=str(project),
            )

        cmd = ["dbt", *args, "--project-dir", str(project)]
        env = os.environ.copy()
        env["DBT_PROFILES_DIR"] = str(profiles)
        env.setdefault("DBT_SEND_ANONYMOUS_USAGE_STATS", "False")

        completed = subprocess.run(
            cmd,
            cwd=str(project),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        result = DbtRunResult(
            command=tuple(cmd),
            returncode=completed.returncode,
            stdout=completed.stdout[-8000:],
            stderr=completed.stderr[-8000:],
            skipped=False,
        )
        if raise_on_error and not result.ok:
            transformation_failure(
                f"dbt command failed: {' '.join(args)} (exit {result.returncode})",
                stage=stage,
                returncode=result.returncode,
                stderr_tail=result.stderr[-500:] if result.stderr else "",
            )
        return result
