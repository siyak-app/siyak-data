"""The morphology pack ``morphology.qac`` (spec §5.3, docs/pack-format.md §4.4, §7).

Inputs: the QAC v0.4 file, its NOTICE, the license text, and the Tanzil
Uthmani text. Output: ``<id>.sqlite`` (kept for validation) and the published
archive ``<id>.tar.zst`` holding that database plus the QAC file byte-for-byte,
its NOTICE and the license text.

Conversion changes format only: segment text is QAC's Buckwalter form in
Arabic script, lemmas and roots likewise (roots as spaced letters), the POS tag
is QAC's code and every other feature goes into ``features`` under a stable
key. ``words.text_ar`` is Tanzil's text (rule A1 in pipeline/align.py).
No tag is added, removed or corrected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.align import AlignmentReport, align, group_words, render_report, tanzil_words
from pipeline.archive import build_archive
from pipeline.buckwalter import root_to_arabic, to_arabic
from pipeline.build_translation import require_pack, source_version
from pipeline.errors import PipelineError
from pipeline.fetch import verify_cached
from pipeline.qac import QacFile, interpret, parse_qac
from pipeline.schema import SCHEMA_VERSION, PackInfo, finalize, new_database, write_pack_info
from pipeline.sources import Source

QAC_FILE = "quranic-corpus-morphology-0.4.txt"
LICENSE_FILE = "COPYING"
DB_MEMBER = "morphology.sqlite"
NOTICE_MEMBER = "qac/NOTICE"
LICENSE_MEMBER = "qac/COPYING"
QAC_MEMBER = f"qac/{QAC_FILE}"
ARCHIVE_MEMBERS = (DB_MEMBER, LICENSE_MEMBER, NOTICE_MEMBER, QAC_MEMBER)

#: The morphology tables of content.db (spec §5.3) without foreign keys.
MORPHOLOGY_DDL = """
CREATE TABLE words (
  id         INTEGER PRIMARY KEY,
  verse_id   INTEGER NOT NULL,
  position   INTEGER NOT NULL,
  text_ar    TEXT NOT NULL,
  translit   TEXT,
  gloss_en   TEXT,
  UNIQUE (verse_id, position)
);
CREATE TABLE roots (
  id    INTEGER PRIMARY KEY,
  root  TEXT NOT NULL UNIQUE
);
CREATE TABLE lemmas (
  id       INTEGER PRIMARY KEY,
  lemma    TEXT NOT NULL UNIQUE,
  root_id  INTEGER
);
CREATE TABLE word_segments (
  word_id   INTEGER NOT NULL,
  idx       INTEGER NOT NULL,
  kind      TEXT NOT NULL CHECK (kind IN ('prefix','stem','suffix')),
  text_ar   TEXT NOT NULL,
  pos       TEXT NOT NULL,
  lemma_id  INTEGER,
  root_id   INTEGER,
  features  TEXT,
  PRIMARY KEY (word_id, idx)
) WITHOUT ROWID;
"""


@dataclass
class MorphologyRows:
    """Rows of the four morphology tables, in insertion order."""

    words: list[tuple[int, int, int, str]] = field(default_factory=list)
    roots: dict[str, int] = field(default_factory=dict)
    lemmas: dict[str, tuple[int, int | None]] = field(default_factory=dict)
    segments: list[tuple[int, int, str, str, str, int | None, int | None, str | None]] = field(
        default_factory=list
    )


def features_json(features: dict[str, str]) -> str | None:
    """Serialize features compactly with sorted keys; NULL when there are none."""
    if not features:
        return None
    return json.dumps(features, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def derive_rows(
    qac: QacFile, verses: dict[tuple[int, int], str], ids: dict[tuple[int, int], int]
) -> tuple[MorphologyRows, AlignmentReport]:
    """Align QAC with Tanzil and derive the table rows.

    Raises if the alignment gate fails; the caller writes the report first via
    :func:`alignment_report`.
    """
    grouped = group_words(qac.segments)
    report = align(verses, grouped)
    if report.failures():
        return MorphologyRows(), report
    rows = MorphologyRows()
    conflicts: dict[str, set[str | None]] = {}
    word_id = 0
    for key in sorted(verses, key=lambda k: ids[k]):
        surah, ayah = key
        words = tanzil_words(verses[key], f"{surah}:{ayah}")
        for word, segments in zip(words, grouped[key], strict=True):
            word_id += 1
            rows.words.append((word_id, ids[key], word.position, word.text_ar))
            for seg in segments:
                parsed = interpret(seg)
                root = root_to_arabic(parsed.root) if parsed.root else None
                root_id = rows.roots.setdefault(root, len(rows.roots) + 1) if root else None
                lemma_id = None
                if parsed.lemma:
                    lemma = to_arabic(parsed.lemma)
                    known = rows.lemmas.setdefault(lemma, (len(rows.lemmas) + 1, root_id))
                    if known[1] != root_id:
                        conflicts.setdefault(lemma, {_root_name(rows, known[1])}).add(root)
                    lemma_id = known[0]
                rows.segments.append(
                    (
                        word_id,
                        seg.segment,
                        parsed.kind,
                        to_arabic(seg.form),
                        parsed.pos,
                        lemma_id,
                        root_id,
                        features_json(parsed.features),
                    )
                )
    if conflicts:
        sample = "; ".join(f"{k}: {sorted(map(str, v))}" for k, v in list(conflicts.items())[:10])
        raise PipelineError(
            f"{len(conflicts)} lemma(s) occur with different roots, but lemmas.lemma is "
            f"UNIQUE with one root_id (schema decision needed). First: {sample}"
        )
    return rows, report


def _root_name(rows: MorphologyRows, root_id: int | None) -> str | None:
    return next((r for r, i in rows.roots.items() if i == root_id), None)


def write_database(out: Path, info: PackInfo, rows: MorphologyRows) -> Path:
    """Write the morphology SQLite database."""
    conn = new_database(out)
    write_pack_info(conn, info)
    conn.executescript(MORPHOLOGY_DDL)
    conn.executemany(
        "INSERT INTO roots (id, root) VALUES (?, ?)",
        sorted((i, r) for r, i in rows.roots.items()),
    )
    conn.executemany(
        "INSERT INTO lemmas (id, lemma, root_id) VALUES (?, ?, ?)",
        sorted((i, lemma, root) for lemma, (i, root) in rows.lemmas.items()),
    )
    conn.executemany(
        "INSERT INTO words (id, verse_id, position, text_ar) VALUES (?, ?, ?, ?)", rows.words
    )
    conn.executemany(
        "INSERT INTO word_segments (word_id, idx, kind, text_ar, pos, lemma_id, root_id, "
        "features) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows.segments,
    )
    finalize(conn)
    return out


def alignment_report(report: AlignmentReport, reports_dir: Path) -> Path:
    """Write the Markdown and JSON alignment reports; return the Markdown path."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    md = reports_dir / "qac-alignment.md"
    md.write_text(render_report(report), encoding="utf-8")
    data = {
        "levels": dict(report.levels()),
        "count_mismatches": [
            {"surah": s, "ayah": a, "tanzil_words": t, "qac_words": q}
            for s, a, t, q in report.count_mismatches
        ],
        "words": [
            {"location": f"{w.surah}:{w.ayah}:{w.position}", "level": w.level,
             "tanzil": w.tanzil, "qac": w.qac}
            for w in report.words
            if w.level != "exact"
        ],
    }  # fmt: skip
    (reports_dir / "qac-alignment.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return md


def build_morphology_pack(
    source: Source,
    verses: dict[tuple[int, int], str],
    ids: dict[tuple[int, int], int],
    out_dir: Path,
    *,
    built_at: str,
    mtime: int,
) -> list[Path]:
    """Build ``<id>.sqlite`` and ``<id>.tar.zst``; return both paths."""
    pack = require_pack(source)
    if pack.type != "morphology":
        raise PipelineError(f"{source.path}: pack type is '{pack.type}', not 'morphology'")
    qac_path = verify_cached(source, QAC_FILE)
    license_path = verify_cached(source, LICENSE_FILE)
    notice_path = source.path.parent / "NOTICE"
    qac = parse_qac(qac_path)
    if notice_path.read_text(encoding="utf-8").rstrip("\n") != qac.notice:
        raise PipelineError(f"{notice_path} is not the verbatim header of {QAC_FILE}")
    rows, report = derive_rows(qac, verses, ids)
    md = alignment_report(report, out_dir / "reports")
    failures = report.failures()
    if failures:
        shown = "\n  ".join(failures[:20])
        raise PipelineError(
            f"QAC alignment failed for {len(failures)} item(s); see {md}\n  {shown}"
        )
    info = PackInfo(
        pack.id, pack.type, pack.version, SCHEMA_VERSION, built_at, source_version(source)
    )
    db = write_database(out_dir / f"{pack.id}.sqlite", info, rows)
    members = [
        (DB_MEMBER, db),
        (LICENSE_MEMBER, license_path),
        (NOTICE_MEMBER, notice_path),
        (QAC_MEMBER, qac_path),
    ]
    return [db, build_archive(out_dir, pack.id, members, mtime)]
