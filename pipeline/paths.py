"""Filesystem locations used by every pipeline step.

All paths are relative to the repository root so the pipeline behaves the same
locally and in CI. ``SIYAK_DATA_ROOT`` overrides the root (used by tests);
``SIYAK_DATA_SOURCES``, ``SIYAK_DATA_CACHE`` and ``SIYAK_DATA_DIST`` override
single directories (used by the ``--profile fixtures`` build).
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Return the repository root (``SIYAK_DATA_ROOT`` or the parent of ``pipeline/``)."""
    override = os.environ.get("SIYAK_DATA_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parent.parent


def _override(variable: str, default: Path) -> Path:
    value = os.environ.get(variable)
    return Path(value).resolve() if value else default


def sources_dir() -> Path:
    """Directory holding one ``source.toml`` per data source."""
    return _override("SIYAK_DATA_SOURCES", repo_root() / "sources")


def cache_dir() -> Path:
    """Download cache for pinned source files (gitignored)."""
    return _override("SIYAK_DATA_CACHE", repo_root() / ".cache")


def dist_dir() -> Path:
    """Build output directory (gitignored)."""
    return _override("SIYAK_DATA_DIST", repo_root() / "dist")


def schema_file() -> Path:
    """The content.db DDL that every pack must satisfy."""
    return repo_root() / "schema" / "content.sql"


def data_dir() -> Path:
    """Small hand-written data reviewed like code (CSV/TOML)."""
    return repo_root() / "data"
