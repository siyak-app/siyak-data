"""Translation packs: one SQLite file with ``pack_info`` and ``translations``.

The table layout matches content.db (spec §5.1) without the foreign key to
``packs``, which a pack does not contain. Verse ids are computed from the
Tanzil metadata, so a pack can be built without core.db.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from pipeline.errors import PipelineError
from pipeline.fetch import verify_cached
from pipeline.schema import SCHEMA_VERSION, PackInfo, finalize, new_database, write_pack_info
from pipeline.sources import PackMeta, Source
from pipeline.tanzil import Metadata, parse_translation

TRANSLATIONS_DDL = """
CREATE TABLE translations (
  pack_id   TEXT NOT NULL,
  verse_id  INTEGER NOT NULL,
  text      TEXT NOT NULL,
  PRIMARY KEY (pack_id, verse_id)
) WITHOUT ROWID
"""


def verse_ids(metadata: Metadata) -> dict[tuple[int, int], int]:
    """Map (surah, ayah) to the global verse id 1..6236, in Mushaf order."""
    ids: dict[tuple[int, int], int] = {}
    for surah in sorted(metadata.surahs, key=lambda s: s.number):
        for ayah in range(1, surah.ayah_count + 1):
            ids[(surah.number, ayah)] = len(ids) + 1
    return ids


def require_pack(source: Source) -> PackMeta:
    """Return the ``[pack]`` table of a source or fail."""
    if source.pack is None:
        raise PipelineError(f"{source.path}: no [pack] table")
    return source.pack


def source_version(source: Source) -> str:
    """The version string recorded in ``pack_info.source_version``."""
    return "; ".join(f"{f.name}@{f.version}" for f in source.files)


def packs_row(source: Source, *, installed_at: str, bundled: bool) -> dict[str, Any]:
    """The ``packs`` row for a source's pack (used by core.db and by install)."""
    pack = require_pack(source)
    meta = {
        "title": pack.title,
        "license_terms": pack.license_terms,
        "source_version": source_version(source),
        **pack.meta,
    }
    if pack.description:
        meta["description"] = pack.description
    return {
        "id": pack.id,
        "type": pack.type,
        "lang": pack.lang,
        "title": pack.title["en"],
        "author": pack.author,
        "version": pack.version,
        "license": pack.license,
        "attribution": pack.attribution,
        "citation_json": json.dumps(pack.citation, ensure_ascii=False, sort_keys=True),
        "meta_json": json.dumps(meta, ensure_ascii=False, sort_keys=True),
        "installed_at": installed_at,
        "bundled": int(bundled),
    }


def translation_rows(source: Source, ids: dict[tuple[int, int], int]) -> list[tuple[int, str]]:
    """Read a source's translation file and return ``(verse_id, text)`` sorted by verse id."""
    if len(source.files) != 1:
        raise PipelineError(f"{source.path}: a translation source must have exactly one file")
    path = verify_cached(source, source.files[0].name)
    parsed = parse_translation(path)
    unknown = sorted(set(parsed.verses) - set(ids))
    if unknown:
        s, a = unknown[0]
        raise PipelineError(
            f"{path}: {len(unknown)} verse(s) not in the Quran metadata, first {s}:{a}"
        )
    return sorted((ids[key], text) for key, text in parsed.verses.items())


def build_translation_pack(
    source: Source, ids: dict[tuple[int, int], int], out_dir: Path, built_at: str
) -> Path:
    """Build ``<out_dir>/<pack id>.sqlite`` and return its path."""
    pack = require_pack(source)
    if pack.type != "translation":
        raise PipelineError(f"{source.path}: pack type is '{pack.type}', not 'translation'")
    rows = translation_rows(source, ids)
    out = out_dir / f"{pack.id}.sqlite"
    conn = new_database(out)
    info = PackInfo(
        pack.id, pack.type, pack.version, SCHEMA_VERSION, built_at, source_version(source)
    )
    write_pack_info(conn, info)
    conn.execute(TRANSLATIONS_DDL)
    conn.executemany(
        "INSERT INTO translations (pack_id, verse_id, text) VALUES (?, ?, ?)",
        [(pack.id, verse_id, text) for verse_id, text in rows],
    )
    finalize(conn)
    return out


def upsert_packs_row(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    """Insert or update one ``packs`` row.

    Uses ``ON CONFLICT … DO UPDATE``, never ``INSERT OR REPLACE``: REPLACE deletes
    the old row first, and with foreign keys on, ``ON DELETE CASCADE`` would then
    remove the pack's translations/tafsir rows.
    """
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    updates = ", ".join(f"{c} = excluded.{c}" for c in row if c != "id")
    conn.execute(
        f"INSERT INTO packs ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}",
        list(row.values()),
    )
