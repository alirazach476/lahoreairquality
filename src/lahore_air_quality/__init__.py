"""Lahore Air Quality Intelligence Platform — root meta-package.

Workspace members under ``apps/``, ``ingestion/``, ``ml/``, and
``orchestration/`` hold the real application code.

Shared configuration lives in :mod:`lahore_air_quality.config`.
"""

from lahore_air_quality.config import Settings, get_settings, load_settings

__version__ = "0.1.0"

__all__ = [
    "Settings",
    "__version__",
    "get_settings",
    "load_settings",
]

# Database helpers are available via ``lahore_air_quality.db`` to keep the
# root import light for non-persistence callers.
