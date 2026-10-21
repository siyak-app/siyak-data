"""Validation gates for the morphology pack (spec §5.3.1, §15.2).

- The archive holds exactly the expected members; its database is the one
  that was built.
- The original QAC file inside the archive has the pinned v0.4 sha256
  (proof it is unmodified); NOTICE and the license text are present and match
  their sources.
- One derived segment row per segment line of the QAC file, in file order,
  whose text is the Arabic form of the QAC Buckwalter form.
- Every verse is covered and its words join back to the Tanzil text (rule A1);
  the alignment gate (A2, A3) passes.
- Every lemma_id and root_id resolves, and the pack installs into a content
  database with foreign keys on.
"""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from pipeline.align import align, group_words
from pipeline.archive import extract_archive
from pipeline.buckwalter import to_arabic
from pipeline.build_morphology import (
    DB_MEMBER,
    LICENSE_FILE,
    LICENSE_MEMBER,
    NOTICE_MEMBER,
    QAC_FILE,
    QAC_MEMBER,
)
from pipeline.build_translation import require_pack, source_version
from pipeline.compress import frame_content_size
from pipeline.errors import PipelineError
from pipeline.fetch import sha256_file, verify_cached
from pipeline.gates import Report, install_into_core_copy
from pipeline.install import ARCHIVE_LAYOUT, check_pack_structure
from pipeline.qac import parse_qac
from pipeline.schema import SCHEMA_VERSION, read_pack_info
from pipeline.sources import Source


def check_morphology_pack(dist: Path, source: Source, core: Path, report: Report) -> None:
    """Run every morphology gate on ``dist/<id>.tar.zst``."""
    pack = require_pack(source)
    archive = dist / f"{pack.id}.tar.zst"
    built = dist / f"{pack.id}.sqlite"
    if not report.check(archive.exists(), f"{archive.name}: not built"):
        return
    with tempfile.TemporaryDirectory(prefix="siyak-validate-") as tmp:
        try:
            _, members = ARCHIVE_LAYOUT[pack.type]
            size = frame_content_size(archive)
            files = extract_archive(archive, Path(tmp), expected=set(members), max_size=size)
        except PipelineError as exc:
            report.check(False, str(exc))
            return
        _check_members(files, source, built, report)
        _check_database(files[DB_MEMBER], source, core, report)
        report.info.append(f"{archive.name}: {archive.stat().st_size:,} bytes ({size:,} as tar)")


def _check_members(files: dict[str, Path], source: Source, built: Path, report: Report) -> None:
    qac = source.file(QAC_FILE)
    license_file = source.file(LICENSE_FILE)
    report.check(
        sha256_file(files[QAC_MEMBER]) == qac.sha256,
        f"{QAC_MEMBER}: sha256 differs from the pinned v{qac.version} file (it must be unmodified)",
    )
    report.check(
        sha256_file(files[LICENSE_MEMBER]) == license_file.sha256,
        f"{LICENSE_MEMBER}: sha256 differs from the pinned license text",
    )
    notice = source.path.parent / "NOTICE"
    report.check(
        files[NOTICE_MEMBER].read_bytes() == notice.read_bytes(),
        f"{NOTICE_MEMBER}: differs from {notice}",
    )
    report.check(
        built.exists() and files[DB_MEMBER].read_bytes() == built.read_bytes(),
        f"{DB_MEMBER} in the archive differs from the built {built.name}",
    )


def _check_database(db: Path, source: Source, core: Path, report: Report) -> None:
    pack = require_pack(source)
    with closing(sqlite3.connect(db)) as conn:
        try:
            check_pack_structure(conn, pack.type)
            info = read_pack_info(conn)
        except (PipelineError, ValueError, sqlite3.Error) as exc:
            report.check(False, f"{pack.id}: {exc}")
            return
        expected = (pack.id, pack.type, pack.version, SCHEMA_VERSION, source_version(source))
        actual = (info.id, info.type, info.version, info.schema_version, info.source_version)
        report.check(actual == expected, f"{pack.id}: pack_info {actual} != {expected}")
        _check_segments(conn, source, report)
        _check_words(conn, core, report)
        _check_references(conn, report)
        counts = {
            t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("words", "word_segments", "roots", "lemmas")
        }
    report.info.append(f"{pack.id}: " + ", ".join(f"{t} {n:,}" for t, n in counts.items()))
    try:
        install_into_core_copy(core, [(db, source)])
    except (PipelineError, sqlite3.Error) as exc:
        report.check(False, f"{pack.id}: install failed: {exc}")


def _check_segments(conn: sqlite3.Connection, source: Source, report: Report) -> None:
    """One row per QAC segment line, in file order, text = Arabic form of the QAC form."""
    segments = parse_qac(verify_cached(source, QAC_FILE)).segments
    rows = conn.execute(
        "SELECT s.idx, s.text_ar, s.pos FROM word_segments s "
        "JOIN words w ON w.id = s.word_id ORDER BY w.id, s.idx"
    ).fetchall()
    if not report.check(
        len(rows) == len(segments),
        f"word_segments: {len(rows):,} rows, the QAC file has {len(segments):,} segments",
    ):
        return
    for seg, (idx, text, pos) in zip(segments, rows, strict=True):
        if (idx, text, pos) != (seg.segment, to_arabic(seg.form), seg.tag):
            report.check(
                False,
                f"QAC {seg.location}: derived row {(idx, text, pos)} does not match "
                f"{(seg.segment, to_arabic(seg.form), seg.tag)}",
            )
            return


def _check_words(conn: sqlite3.Connection, core: Path, report: Report) -> None:
    """Every verse has words, and they join back to the Tanzil text (rule A1)."""
    with closing(sqlite3.connect(core)) as core_conn:
        verses = {
            vid: (surah, ayah, text)
            for vid, surah, ayah, text in core_conn.execute(
                "SELECT id, surah, ayah, text_uthmani FROM verses"
            )
        }
    joined: dict[int, list[str]] = {}
    for verse_id, text in conn.execute(
        "SELECT verse_id, text_ar FROM words ORDER BY verse_id, position"
    ):
        joined.setdefault(verse_id, []).append(text)
    report.check(
        set(joined) == set(verses),
        f"words: cover {len(joined):,} verses, core.db has {len(verses):,}",
    )
    for verse_id, parts in joined.items():
        surah, ayah, text = verses.get(verse_id, (0, 0, ""))
        if " ".join(parts) != text:
            report.check(False, f"{surah}:{ayah}: words do not join back to text_uthmani")
            return


def _check_references(conn: sqlite3.Connection, report: Report) -> None:
    dangling = conn.execute(
        "SELECT "
        "(SELECT count(*) FROM word_segments WHERE lemma_id IS NOT NULL "
        " AND lemma_id NOT IN (SELECT id FROM lemmas)), "
        "(SELECT count(*) FROM word_segments WHERE root_id IS NOT NULL "
        " AND root_id NOT IN (SELECT id FROM roots)), "
        "(SELECT count(*) FROM lemmas WHERE root_id IS NOT NULL "
        " AND root_id NOT IN (SELECT id FROM roots)), "
        "(SELECT count(*) FROM word_segments WHERE word_id NOT IN (SELECT id FROM words))"
    ).fetchone()
    for count, what in zip(
        dangling,
        ("segment lemma_id", "segment root_id", "lemma root_id", "segment word_id"),
        strict=True,
    ):
        report.check(count == 0, f"morphology: {count} {what} value(s) do not resolve")


def check_alignment(_dist: Path, source: Source, core: Path, report: Report) -> None:
    """Re-run the alignment gate against core.db's Uthmani text."""
    with closing(sqlite3.connect(core)) as conn:
        verses = {
            (s, a): text
            for s, a, text in conn.execute("SELECT surah, ayah, text_uthmani FROM verses")
        }
    result = align(verses, group_words(parse_qac(verify_cached(source, QAC_FILE)).segments))
    for failure in result.failures()[:50]:
        report.check(False, f"alignment: {failure}")
    levels = result.levels()
    report.info.append(
        "alignment: " + ", ".join(f"{level} {levels[level]:,}" for level in sorted(levels))
    )
