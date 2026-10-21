"""Shared pieces of the validation gates: the report and the reference install."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.build_translation import packs_row
from pipeline.errors import PipelineError
from pipeline.install import install_pack
from pipeline.schema import apply_content_schema
from pipeline.sources import Source


@dataclass
class Report:
    """Collected failures and informational lines of one validation run."""

    failures: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def check(self, ok: bool, message: str) -> bool:
        if not ok:
            self.failures.append(message)
        return ok


def install_into_core_copy(
    core: Path, packs: list[tuple[Path, Source]], schema_sql: list[str] | None = None
) -> sqlite3.Connection:
    """Create a content database (from schema/content.sql or ``schema_sql`` migrations),
    load core.db's data into it, install the packs with foreign keys on, and return it.
    """
    conn = sqlite3.connect(":memory:")
    if schema_sql is None:
        apply_content_schema(conn)
    else:
        for script in schema_sql:
            conn.executescript(script)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("ATTACH DATABASE ? AS core", (str(core),))
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM core.sqlite_master WHERE type = 'table' "
            "AND sql NOT LIKE 'CREATE VIRTUAL%' AND name NOT LIKE '%fts_%'"
        )
    ]
    with conn:
        for table in ["surahs", "verses", *[t for t in tables if t not in ("surahs", "verses")]]:
            columns = [r[1] for r in conn.execute(f"PRAGMA core.table_info({table})")]
            names = ", ".join(columns)
            conn.execute(f"INSERT INTO main.{table} ({names}) SELECT {names} FROM core.{table}")
    conn.execute("DETACH DATABASE core")
    for path, source in packs:
        install_pack(conn, path, packs_row(source, installed_at="test", bundled=False))
    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise PipelineError(f"foreign key violations after install: {problems[:5]}")
    return conn
