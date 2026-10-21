"""Reference implementation of the app's pack install (spec §6.4, §14.3).

The app installs a pack by attaching it to content.db and copying only the
expected columns of the expected tables, in one transaction: upsert the
``packs`` row (``ON CONFLICT DO UPDATE``; see ``upsert_packs_row``), delete the
pack's old rows, copy the new ones, refresh FTS. This module does the same, so the
schema-compatibility test (tests/test_schema_compat.py) and ``validate`` prove
that every built pack installs into a database created from the content schema
(or from the app's own migrations).

A pack is untrusted input for the app: before anything is copied, its
``sqlite_master`` is checked to hold only plain tables and indexes from an
allow-list, and its ``pack_info`` must match the expected pack.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from pipeline.archive import extract_archive
from pipeline.build_translation import upsert_packs_row
from pipeline.errors import PipelineError
from pipeline.schema import SCHEMA_VERSION, read_pack_info

#: Tables (and their columns) a pack of each type may contain besides pack_info.
PACK_TABLES: dict[str, dict[str, tuple[str, ...]]] = {
    "translation": {"translations": ("pack_id", "verse_id", "text")},
    "tafsir": {
        "tafsir": ("id", "pack_id", "verse_from", "verse_to"),
        "tafsir_paragraphs": ("tafsir_id", "idx", "text", "part", "page"),
    },
    "morphology": {
        "words": ("id", "verse_id", "position", "text_ar", "translit", "gloss_en"),
        "roots": ("id", "root"),
        "lemmas": ("id", "lemma", "root_id"),
        "word_segments": (
            "word_id", "idx", "kind", "text_ar", "pos", "lemma_id", "root_id", "features",
        ),
    },
}  # fmt: skip

#: Archive packs: the database member and every member the archive must hold.
ARCHIVE_LAYOUT: dict[str, tuple[str, frozenset[str]]] = {
    "morphology": (
        "morphology.sqlite",
        frozenset(
            {
                "morphology.sqlite",
                "qac/COPYING",
                "qac/NOTICE",
                "qac/quranic-corpus-morphology-0.4.txt",
            }
        ),
    ),
}

PACK_INFO_COLUMNS = ("id", "type", "version", "schema_version", "built_at", "source_version")


def check_pack_structure(conn: sqlite3.Connection, pack_type: str, schema: str = "main") -> None:
    """Fail unless the pack holds only allowed tables/columns and plain indexes."""
    allowed = PACK_TABLES.get(pack_type)
    if allowed is None:
        raise PipelineError(f"no install rule for pack type '{pack_type}'")
    expected = {"pack_info": PACK_INFO_COLUMNS, **allowed}
    objects = conn.execute(
        f"SELECT type, name, tbl_name, sql FROM {schema}.sqlite_master"
    ).fetchall()
    for kind, name, table, sql in objects:
        if kind not in ("table", "index"):
            raise PipelineError(f"pack contains a {kind} '{name}'; only tables and indexes allowed")
        if kind == "table" and str(sql or "").upper().startswith("CREATE VIRTUAL"):
            raise PipelineError(f"pack contains a virtual table '{name}'")
        if table not in expected:
            raise PipelineError(f"pack contains unexpected table '{table}'")
    present = {name for kind, name, _t, _s in objects if kind == "table"}
    missing = sorted(set(expected) - present)
    if missing:
        raise PipelineError(f"pack is missing table(s): {', '.join(missing)}")
    for table, columns in expected.items():
        actual = tuple(
            row[1] for row in conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall()
        )
        if actual != columns:
            raise PipelineError(f"pack table '{table}' has columns {actual}, expected {columns}")


def install_pack(conn: sqlite3.Connection, pack_path: Path, packs_row: dict[str, Any]) -> None:
    """Install one pack database into ``conn`` (a content.db) the way the app does.

    ``packs_row`` is the row the app writes to ``packs`` from the manifest entry.
    """
    pack_id, pack_type = str(packs_row["id"]), str(packs_row["type"])
    conn.execute("ATTACH DATABASE ? AS pack", (str(pack_path),))
    try:
        check_pack_structure(conn, pack_type, "pack")
        info = read_pack_info(conn, "pack")
        if (info.id, info.type) != (pack_id, pack_type):
            raise PipelineError(
                f"{pack_path}: pack_info says {info.id}/{info.type}, expected {pack_id}/{pack_type}"
            )
        if info.schema_version != SCHEMA_VERSION:
            raise PipelineError(
                f"{pack_path}: schema_version {info.schema_version}, expected {SCHEMA_VERSION}"
            )
        with conn:
            # The packs row comes first: the copied rows reference it (foreign key).
            upsert_packs_row(conn, packs_row)
            _copy_rows(conn, pack_id, pack_type)
    finally:
        conn.execute("DETACH DATABASE pack")


#: Insert order that satisfies the foreign keys (roots ← lemmas, words ← segments).
_MORPHOLOGY_ORDER = ("roots", "lemmas", "words", "word_segments")


def _copy_rows(conn: sqlite3.Connection, pack_id: str, pack_type: str) -> None:
    if pack_type == "translation":
        conn.execute("DELETE FROM translations_fts WHERE pack_id = ?", (pack_id,))
        conn.execute("DELETE FROM translations WHERE pack_id = ?", (pack_id,))
        # pack_id is taken from the manifest, never from the pack's rows.
        conn.execute(
            "INSERT INTO translations (pack_id, verse_id, text) "
            "SELECT ?, verse_id, text FROM pack.translations",
            (pack_id,),
        )
        conn.execute(
            "INSERT INTO translations_fts (text, pack_id, verse_id) "
            "SELECT text, pack_id, verse_id FROM translations WHERE pack_id = ?",
            (pack_id,),
        )
        return
    if pack_type == "tafsir":
        _copy_tafsir(conn, pack_id)
        return
    if pack_type == "morphology":
        # v1 keeps one morphology pack at a time: the morphology tables have no
        # pack_id, so installing one replaces all morphology data (pack-format §4.4).
        conn.execute("DELETE FROM packs WHERE type = 'morphology' AND id != ?", (pack_id,))
        for table in reversed(_MORPHOLOGY_ORDER):
            conn.execute(f"DELETE FROM {table}")
        for table in _MORPHOLOGY_ORDER:
            names = ", ".join(PACK_TABLES["morphology"][table])
            conn.execute(f"INSERT INTO main.{table} ({names}) SELECT {names} FROM pack.{table}")
        return
    raise PipelineError(f"no install rule for pack type '{pack_type}'")


def install_archive_pack(
    conn: sqlite3.Connection,
    archive: Path,
    packs_row: dict[str, Any],
    work_dir: Path,
    max_size: int,
) -> dict[str, Path]:
    """Unpack an archive pack safely, install its database, return its files.

    The app keeps the returned non-database files (e.g. the original QAC file
    and its NOTICE) in the pack's directory under app data.
    """
    layout = ARCHIVE_LAYOUT.get(str(packs_row["type"]))
    if layout is None:
        raise PipelineError(f"pack type '{packs_row['type']}' is not an archive pack")
    db_member, members = layout
    files = extract_archive(archive, work_dir, expected=set(members), max_size=max_size)
    install_pack(conn, files[db_member], packs_row)
    return files


def _copy_tafsir(conn: sqlite3.Connection, pack_id: str) -> None:
    """Copy a tafsir pack, giving its passages new ids in content.db.

    ``tafsir.id`` is global in content.db, so the pack's ids cannot be kept. The
    pack's passages never overlap, so ``verse_from`` identifies a passage within
    the pack and maps old ids to new ones.
    """
    duplicates = conn.execute(
        "SELECT count(*) - count(DISTINCT verse_from) FROM pack.tafsir"
    ).fetchone()[0]
    if duplicates:
        raise PipelineError(f"tafsir pack '{pack_id}' has passages with the same verse_from")
    conn.execute(
        "DELETE FROM tafsir_paragraphs WHERE tafsir_id IN "
        "(SELECT id FROM tafsir WHERE pack_id = ?)",
        (pack_id,),
    )
    conn.execute("DELETE FROM tafsir WHERE pack_id = ?", (pack_id,))
    conn.execute(
        "INSERT INTO tafsir (pack_id, verse_from, verse_to) "
        "SELECT ?, verse_from, verse_to FROM pack.tafsir ORDER BY verse_from",
        (pack_id,),
    )
    conn.execute(
        "INSERT INTO tafsir_paragraphs (tafsir_id, idx, text, part, page) "
        "SELECT t.id, p.idx, p.text, p.part, p.page FROM pack.tafsir_paragraphs p "
        "JOIN pack.tafsir pt ON pt.id = p.tafsir_id "
        "JOIN main.tafsir t ON t.pack_id = ? AND t.verse_from = pt.verse_from",
        (pack_id,),
    )
