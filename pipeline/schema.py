"""The content.db schema and the ``pack_info`` table every pack carries.

``schema/content.sql`` is the contract: core.db is built from it and every pack
must install into a database created from it (tests/test_schema_compat.py).
Builds are deterministic so that a rebuild from the same inputs gives the same
sha256: timestamps come from ``SOURCE_DATE_EPOCH``, rows are inserted in sorted
order by the builders, and every database is VACUUMed before it is closed.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipeline.paths import schema_file

#: Version of schema/content.sql; written to ``PRAGMA user_version`` of core.db
#: and to ``pack_info.schema_version`` of every pack.
SCHEMA_VERSION = 2

PACK_INFO_DDL = """
CREATE TABLE pack_info (
  id              TEXT NOT NULL,
  type            TEXT NOT NULL,
  version         TEXT NOT NULL,
  schema_version  INTEGER NOT NULL,
  built_at        TEXT NOT NULL,
  source_version  TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class PackInfo:
    """The single row of a pack's ``pack_info`` table (docs/pack-format.md)."""

    id: str
    type: str
    version: str
    schema_version: int
    built_at: str
    source_version: str


def build_epoch() -> int:
    """Return the build time in seconds since the epoch.

    Uses ``SOURCE_DATE_EPOCH`` when set (release builds), so rebuilds are
    reproducible; otherwise the current time.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    return int(epoch) if epoch else int(datetime.now(UTC).timestamp())


def build_timestamp() -> str:
    """Return the build time (:func:`build_epoch`) as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.fromtimestamp(build_epoch(), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_database(path: Path) -> sqlite3.Connection:
    """Create an empty SQLite file at ``path``, replacing any existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    return sqlite3.connect(path)


def apply_content_schema(conn: sqlite3.Connection) -> None:
    """Create every content.db table and set ``user_version``."""
    conn.executescript(schema_file().read_text(encoding="utf-8"))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def write_pack_info(conn: sqlite3.Connection, info: PackInfo) -> None:
    """Create ``pack_info`` and insert its single row."""
    conn.execute(PACK_INFO_DDL)
    conn.execute(
        "INSERT INTO pack_info VALUES (?, ?, ?, ?, ?, ?)",
        (
            info.id,
            info.type,
            info.version,
            info.schema_version,
            info.built_at,
            info.source_version,
        ),
    )


def read_pack_info(conn: sqlite3.Connection, schema: str = "main") -> PackInfo:
    """Read the single ``pack_info`` row; raise ``ValueError`` if it is not exactly one."""
    rows = conn.execute(
        f"SELECT id, type, version, schema_version, built_at, source_version "
        f"FROM {schema}.pack_info"
    ).fetchall()
    if len(rows) != 1:
        raise ValueError(f"pack_info must have exactly one row, found {len(rows)}")
    r = rows[0]
    return PackInfo(str(r[0]), str(r[1]), str(r[2]), int(r[3]), str(r[4]), str(r[5]))


Shape = dict[str, tuple[object, ...]]


def schema_shape(conn: sqlite3.Connection, schema: str = "main") -> Shape:
    """Structural description of a database schema, independent of DDL formatting.

    Tables map to their columns (name, type, not null, default, primary key) and
    foreign keys; indexes map to their table and columns; virtual tables to the
    module arguments. Comments and whitespace in the DDL do not matter.
    """
    shape: Shape = {}
    objects = conn.execute(
        f"SELECT type, name, tbl_name, sql FROM {schema}.sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for kind, name, table, sql in objects:
        if kind == "table" and str(sql or "").upper().startswith("CREATE VIRTUAL"):
            body = str(sql)[str(sql).upper().index("USING") :]
            shape[f"virtual {name}"] = (" ".join(body.split()),)
        elif kind == "table":
            columns = tuple(
                tuple(r[1:]) for r in conn.execute(f"PRAGMA {schema}.table_info({name})")
            )
            fks = tuple(
                tuple(r[2:]) for r in conn.execute(f"PRAGMA {schema}.foreign_key_list({name})")
            )
            shape[f"table {name}"] = (columns, fks, "WITHOUT ROWID" in str(sql).upper())
        elif kind == "index":
            columns = tuple(r[2] for r in conn.execute(f"PRAGMA {schema}.index_info({name})"))
            shape[f"index {name}"] = (table, columns)
    return shape


def finalize(conn: sqlite3.Connection) -> None:
    """Commit, compact and close a freshly built database."""
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
