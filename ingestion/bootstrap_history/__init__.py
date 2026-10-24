"""Historical bootstrap from OpenAQ + Open-Meteo into existing raw tables.

Default mode is **plan only**. Use ``--execute`` to import.
Use ``--weather-only`` to skip OpenAQ (no API key) and import Open-Meteo
archive weather only (model/reanalysis — not ground stations).
Never synthesizes observations.
"""

from ingestion.bootstrap_history.plan import BootstrapPlan, build_bootstrap_plan
from ingestion.bootstrap_history.runner import execute_bootstrap

__all__ = [
    "BootstrapPlan",
    "build_bootstrap_plan",
    "execute_bootstrap",
]
