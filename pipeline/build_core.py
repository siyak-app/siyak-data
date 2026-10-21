"""core.db: the database bundled with the app installer (spec §6.2).

Contents: Tanzil Uthmani and Simple Clean text with metadata, Turkish surah
names (data/surah-names-tr.csv), the bundled translation packs, the notices
that must ship with the data, and filled search indexes. ``user_version`` is the
schema version, so the app copies it to content.db and treats it as migrated.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pipeline.build_translation import (
    packs_row,
    require_pack,
    translation_rows,
    upsert_packs_row,
    verse_ids,
)
from pipeline.errors import PipelineError
from pipeline.fetch import verify_cached
from pipeline.normalize import normalize
from pipeline.paths import data_dir
from pipeline.schema import apply_content_schema, finalize, new_database
from pipeline.sources import Source
from pipeline.tanzil import Metadata, QuranText, parse_metadata, parse_quran_xml

UTHMANI = "quran-uthmani.xml"
SIMPLE_CLEAN = "quran-simple-clean.xml"
METADATA = "quran-data.xml"


@dataclass(frozen=True)
class TanzilInputs:
    """Parsed Tanzil files used by core.db."""

    uthmani: QuranText
    clean: QuranText
    metadata: Metadata


def load_tanzil(tanzil: Source) -> TanzilInputs:
    """Verify and parse the three pinned Tanzil files."""
    return TanzilInputs(
        uthmani=parse_quran_xml(verify_cached(tanzil, UTHMANI)),
        clean=parse_quran_xml(verify_cached(tanzil, SIMPLE_CLEAN)),
        metadata=parse_metadata(verify_cached(tanzil, METADATA)),
    )


def load_turkish_names(path: Path | None = None) -> dict[int, str]:
    """Read data/surah-names-tr.csv as {surah number: name}."""
    csv_path = path or data_dir() / "surah-names-tr.csv"
    with csv_path.open(encoding="utf-8", newline="") as fh:
        return {int(row["number"]): row["name_tr"] for row in csv.DictReader(fh)}


def _check_texts_agree(inputs: TanzilInputs) -> None:
    """Both texts must list the same verses and the same basmala positions."""
    u = [(a.surah, a.ayah, a.bismillah is None) for a in inputs.uthmani.verses]
    c = [(a.surah, a.ayah, a.bismillah is None) for a in inputs.clean.verses]
    if u != c:
        first = next(i for i, (x, y) in enumerate(zip(u, c, strict=False)) if x != y)
        raise PipelineError(
            f"Uthmani and Simple Clean differ in verse structure at index {first}: "
            f"{u[first]} vs {c[first]}"
        )


def _notice_rows(inputs: TanzilInputs, tanzil: Source) -> list[tuple[str, str, str, str, str]]:
    meta = inputs.metadata
    return [
        (
            "tanzil.metadata",
            tanzil.id,
            f"Tanzil Quran metadata (version {meta.version})",
            f"Quran metadata {meta.copyright}. License: {meta.license} "
            "(Creative Commons Attribution). Values taken from the file's attributes.",
            "https://tanzil.net/docs/quran_metadata",
        ),
        ("tanzil.text.simple-clean", tanzil.id, "Tanzil Quran Text (Simple Clean)",
         inputs.clean.notice, tanzil.homepage),
        ("tanzil.text.uthmani", tanzil.id, "Tanzil Quran Text (Uthmani)",
         inputs.uthmani.notice, tanzil.homepage),
    ]  # fmt: skip


def build_core(
    out: Path,
    *,
    tanzil: Source,
    bundled: list[Source],
    built_at: str,
    names_tr: dict[int, str] | None = None,
) -> Path:
    """Build core.db at ``out`` from Tanzil and the bundled translation sources."""
    inputs = load_tanzil(tanzil)
    _check_texts_agree(inputs)
    names = names_tr if names_tr is not None else load_turkish_names()
    ids = verse_ids(inputs.metadata)
    juz = inputs.metadata.juz_of()
    clean_by_key = {(a.surah, a.ayah): a.text for a in inputs.clean.verses}

    conn = new_database(out)
    apply_content_schema(conn)
    _insert_surahs(conn, inputs, names)
    verse_rows = []
    for aya in inputs.uthmani.verses:
        key = (aya.surah, aya.ayah)
        if key not in ids:
            raise PipelineError(f"verse {aya.surah}:{aya.ayah} is not in the Quran metadata")
        verse_rows.append((ids[key], aya.surah, aya.ayah, juz[key], aya.text, clean_by_key[key]))
    verse_rows.sort()
    conn.executemany(
        "INSERT INTO verses (id, surah, ayah, juz, text_uthmani, text_clean) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        verse_rows,
    )
    conn.executemany(
        "INSERT INTO verses_fts (rowid, text_norm) VALUES (?, ?)",
        [(row[0], normalize(row[5])) for row in verse_rows],
    )
    conn.executemany("INSERT INTO notices VALUES (?, ?, ?, ?, ?)", _notice_rows(inputs, tanzil))

    for source in sorted(bundled, key=lambda s: require_pack(s).id):
        _insert_bundled_translation(conn, source, ids, built_at)
    finalize(conn)
    return out


def _insert_surahs(conn: sqlite3.Connection, inputs: TanzilInputs, names: dict[int, str]) -> None:
    bismillah = {a.surah: a.bismillah for a in inputs.uthmani.verses if a.ayah == 1}
    rows = []
    for s in sorted(inputs.metadata.surahs, key=lambda s: s.number):
        if s.number not in names:
            raise PipelineError(f"data/surah-names-tr.csv has no name for surah {s.number}")
        rows.append(
            (
                s.number,
                s.name_ar,
                names[s.number],
                s.name_translit,
                s.revelation_type,
                s.ayah_count,
                bismillah.get(s.number),
            )
        )
    conn.executemany(
        "INSERT INTO surahs (number, name_ar, name_tr, name_en, revelation_type, ayah_count, "
        "bismillah) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def _insert_bundled_translation(
    conn: sqlite3.Connection, source: Source, ids: dict[tuple[int, int], int], built_at: str
) -> None:
    pack = require_pack(source)
    upsert_packs_row(conn, packs_row(source, installed_at=built_at, bundled=True))
    rows = translation_rows(source, ids)
    conn.executemany(
        "INSERT INTO translations (pack_id, verse_id, text) VALUES (?, ?, ?)",
        [(pack.id, verse_id, text) for verse_id, text in rows],
    )
    conn.executemany(
        "INSERT INTO translations_fts (text, pack_id, verse_id) VALUES (?, ?, ?)",
        [(text, pack.id, verse_id) for verse_id, text in rows],
    )
    notice = source.path.parent / "NOTICE"
    if notice.exists():
        conn.execute(
            "INSERT INTO notices VALUES (?, ?, ?, ?, ?)",
            (pack.id, source.id, pack.title["en"], notice.read_text(encoding="utf-8"),
             source.homepage),
        )  # fmt: skip
