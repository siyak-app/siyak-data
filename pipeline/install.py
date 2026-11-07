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
        "tafsir": ("id", "pack_id", "verse_from", "verse_to", "kind"),
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
    "vectors": {"vectors": ("verse_id", "embedding")},
    # A model pack's database holds only pack_info; its files are the model.
    "model": {},
    # Likewise an audio pack: its files are one mp3 per verse (pack-format §4.10).
    "audio": {},
}  # fmt: skip

#: Pack types whose database holds only pack_info. They carry no content tables, so
#: they install under any content schema up to the current one (pack-format §2).
FILES_ONLY_TYPES = frozenset({"model", "audio"})

#: Verses per surah (Hafs, Kufan count), 6,236 in all; the order of the global verse ids.
AYAH_COUNTS = (
    7, 286, 200, 176, 120, 165, 206, 75, 129, 109, 123, 111, 43, 52, 99, 128, 111, 110, 98, 135,
    112, 78, 118, 64, 77, 227, 93, 88, 69, 60, 34, 30, 73, 54, 45, 83, 182, 88, 75, 85, 54, 53,
    89, 59, 37, 35, 38, 29, 18, 45, 60, 49, 62, 55, 78, 96, 29, 22, 24, 13, 14, 11, 11, 18, 12,
    12, 30, 52, 52, 44, 28, 28, 20, 56, 40, 31, 50, 40, 46, 42, 29, 19, 36, 25, 22, 17, 19, 26,
    30, 20, 15, 21, 11, 8, 8, 19, 5, 8, 8, 11, 11, 8, 3, 9, 5, 4, 7, 3, 6, 3, 5, 4, 5, 6,
)  # fmt: skip

AUDIO_DB_MEMBER = "audio.sqlite"
AUDIO_LICENSE_MEMBER = "audio/LICENSE"


def audio_member(surah: int, ayah: int) -> str:
    """The archive member of one verse's recitation: ``audio/SSSAAA.mp3``."""
    return f"audio/{surah:03d}{ayah:03d}.mp3"


def audio_members() -> frozenset[str]:
    """Every member of an audio pack: its database, LICENSE and one mp3 per verse."""
    verses = {
        audio_member(surah, ayah)
        for surah, count in enumerate(AYAH_COUNTS, start=1)
        for ayah in range(1, count + 1)
    }
    return frozenset({AUDIO_DB_MEMBER, AUDIO_LICENSE_MEMBER, *verses})


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
    "model": (
        "model.sqlite",
        frozenset({"model.sqlite", "model/LICENSE", "model/model.onnx", "model/tokenizer.json"}),
    ),
    "audio": (AUDIO_DB_MEMBER, audio_members()),
}

#: The app creates this table when the first vector pack is installed; it is not
#: in schema/content.sql, so adding it did not change SCHEMA_VERSION (pack-format §4.5).
VECTOR_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS main.verse_vectors (
  pack_id   TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
  verse_id  INTEGER NOT NULL REFERENCES verses(id),
  embedding BLOB NOT NULL,
  UNIQUE (pack_id, verse_id)
)
"""

PACK_INFO_COLUMNS = ("id", "type", "version", "schema_version", "built_at", "source_version")


#: The oldest schema a pack of each type may be built for: the one that last
#: changed the tables the pack fills (siyak's ``oldest_schema``). Schema 2 rebuilt
#: tafsir_paragraphs and verses_fts; schema 3 only widened ``packs.type``.
OLDEST_SCHEMA = {
    "translation": 2,
    "tafsir": 2,
    "morphology": 2,
    "vectors": 2,
    "model": 1,
    "audio": 1,
}


def schema_supported(pack_type: str, schema_version: int) -> bool:
    """Whether a pack built for ``schema_version`` installs into the current schema."""
    return OLDEST_SCHEMA.get(pack_type, SCHEMA_VERSION) <= schema_version <= SCHEMA_VERSION


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
        if not schema_supported(pack_type, info.schema_version):
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
    if pack_type == "vectors":
        conn.execute(VECTOR_TABLE_DDL)
        conn.execute("DELETE FROM verse_vectors WHERE pack_id = ?", (pack_id,))
        conn.execute(
            "INSERT INTO verse_vectors (pack_id, verse_id, embedding) "
            "SELECT ?, verse_id, embedding FROM pack.vectors ORDER BY verse_id",
            (pack_id,),
        )
        return
    if pack_type in FILES_ONLY_TYPES:
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

    ``tafsir.id`` is global in content.db, so the pack's ids cannot be kept. A
    pack's passages of one kind never overlap, so ``(verse_from, kind)``
    identifies a passage within the pack and maps old ids to new ones.
    """
    duplicates = conn.execute(
        "SELECT count(*) FROM (SELECT 1 FROM pack.tafsir "
        "GROUP BY verse_from, kind HAVING count(*) > 1)"
    ).fetchone()[0]
    if duplicates:
        raise PipelineError(
            f"tafsir pack '{pack_id}' has two passages with the same start and kind"
        )
    conn.execute(
        "DELETE FROM tafsir_paragraphs WHERE tafsir_id IN "
        "(SELECT id FROM tafsir WHERE pack_id = ?)",
        (pack_id,),
    )
    conn.execute("DELETE FROM tafsir WHERE pack_id = ?", (pack_id,))
    conn.execute(
        "INSERT INTO tafsir (pack_id, verse_from, verse_to, kind) "
        "SELECT ?, verse_from, verse_to, kind FROM pack.tafsir ORDER BY id",
        (pack_id,),
    )
    conn.execute(
        "INSERT INTO tafsir_paragraphs (tafsir_id, idx, text, part, page) "
        "SELECT t.id, p.idx, p.text, p.part, p.page FROM pack.tafsir_paragraphs p "
        "JOIN pack.tafsir pt ON pt.id = p.tafsir_id "
        "JOIN main.tafsir t ON t.pack_id = ? AND t.verse_from = pt.verse_from AND t.kind = pt.kind",
        (pack_id,),
    )
