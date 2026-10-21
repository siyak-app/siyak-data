"""The morphology pack on the synthetic QAC fixture: build, gates, install."""

import shutil
import sqlite3
import tarfile
from contextlib import closing
from pathlib import Path

import pytest

from pipeline.archive import build_archive
from pipeline.build import morphology_sources
from pipeline.build_translation import packs_row
from pipeline.compress import MAX_PACK_SIZE, decompress_pack
from pipeline.errors import PipelineError
from pipeline.gates import install_into_core_copy
from pipeline.install import install_archive_pack, install_pack
from pipeline.sources import load_all
from pipeline.validate import run_validate

ARCHIVE = "morphology.qac.tar.zst"


def unpack(archive: Path, dest: Path) -> Path:
    decompress_pack(archive, dest / "a.tar", MAX_PACK_SIZE)
    with tarfile.open(dest / "a.tar") as tar:
        tar.extractall(dest / "files", filter="data")
    return dest / "files"


def repack(files: Path, out_dir: Path) -> None:
    members = [
        (name, files / name)
        for name in ("morphology.sqlite", "qac/COPYING", "qac/NOTICE",
                     "qac/quranic-corpus-morphology-0.4.txt")
        if (files / name).exists()
    ]  # fmt: skip
    build_archive(out_dir, "morphology.qac", members, mtime=0)


def test_pack_contents(built_fixtures: Path, tmp_path: Path) -> None:
    files = unpack(built_fixtures / ARCHIVE, tmp_path)
    original = Path(__file__).parent / "fixtures" / "cache" / "morphology.qac"
    qac = "quranic-corpus-morphology-0.4.txt"
    assert (files / "qac" / qac).read_bytes() == (original / qac).read_bytes()
    with closing(sqlite3.connect(files / "morphology.sqlite")) as conn:
        first = conn.execute(
            "SELECT w.position, w.text_ar, s.idx, s.kind, s.pos, s.features "
            "FROM words w JOIN word_segments s ON s.word_id = w.id "
            "WHERE w.verse_id = 1 AND w.position = 2 ORDER BY s.idx"
        ).fetchall()
        roots = conn.execute("SELECT root FROM roots ORDER BY id LIMIT 1").fetchone()
    assert [(r[2], r[3], r[4]) for r in first] == [(1, "prefix", "DET"), (2, "stem", "N")]
    assert first[0][5] == '{"prefix":"Al+"}'
    assert roots == ("ب س م",)


def test_morphology_installs_and_one_pack_replaces_another(
    built_fixtures: Path, fixture_sources: None, tmp_path: Path
) -> None:
    (source,) = morphology_sources(load_all())
    files = unpack(built_fixtures / ARCHIVE, tmp_path)
    core = built_fixtures / "core.db"
    conn = install_into_core_copy(core, [(files / "morphology.sqlite", source)])
    assert conn.execute("SELECT count(*) FROM words").fetchone() == (117,)

    # Reinstalling the archive through the archive path gives the same rows.
    row = packs_row(source, installed_at="again", bundled=False)
    install_archive_pack(conn, built_fixtures / ARCHIVE, row, tmp_path / "w", MAX_PACK_SIZE)
    assert conn.execute("SELECT count(*) FROM words").fetchone() == (117,)

    # A different morphology pack replaces all morphology data (one active pack in v1).
    other_db = tmp_path / "other.sqlite"
    shutil.copyfile(files / "morphology.sqlite", other_db)
    with closing(sqlite3.connect(other_db)) as other, other:
        other.execute("UPDATE pack_info SET id = 'morphology.other'")
        other.execute("DELETE FROM word_segments WHERE word_id > 1")
        other.execute("DELETE FROM words WHERE id > 1")
    install_pack(conn, other_db, {**row, "id": "morphology.other"})
    assert conn.execute("SELECT id FROM packs WHERE type = 'morphology'").fetchall() == [
        ("morphology.other",)
    ]
    assert conn.execute("SELECT count(*) FROM words").fetchone() == (1,)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_archive_with_wrong_pack_id_is_refused(
    built_fixtures: Path, fixture_sources: None, tmp_path: Path
) -> None:
    (source,) = morphology_sources(load_all())
    conn = install_into_core_copy(built_fixtures / "core.db", [])
    other = {**packs_row(source, installed_at="t", bundled=False), "id": "morphology.other"}
    with pytest.raises(PipelineError, match=r"pack_info says morphology\.qac"):
        install_archive_pack(conn, built_fixtures / ARCHIVE, other, tmp_path, MAX_PACK_SIZE)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("qac", "must be unmodified"),
        ("notice", "qac/NOTICE: differs"),
        ("drop-notice", "members"),
        ("segment", "word_segments: 159 rows"),
        ("words", "words do not join back"),
    ],
)
def test_morphology_gates(
    built_fixtures: Path, fixture_sources: None, tmp_path: Path, change: str, message: str
) -> None:
    dist = tmp_path / "dist"
    shutil.copytree(built_fixtures, dist)
    files = unpack(dist / ARCHIVE, tmp_path / "work")
    qac = files / "qac" / "quranic-corpus-morphology-0.4.txt"
    if change == "qac":
        qac.write_bytes(qac.read_bytes() + b"\n")
    elif change == "notice":
        (files / "qac" / "NOTICE").write_text("changed\n", encoding="utf-8")
    elif change == "drop-notice":
        (files / "qac" / "NOTICE").unlink()
    else:
        sql = (
            "DELETE FROM word_segments WHERE rowid IN (SELECT rowid FROM word_segments LIMIT 1)"
            if change == "segment"
            else "UPDATE words SET text_ar = 'x' WHERE id = 1"
        )
        for db in (files / "morphology.sqlite", dist / "morphology.qac.sqlite"):
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute(
                    sql.replace(
                        "rowid IN (SELECT rowid", "word_id = 1 AND idx IN (SELECT idx"
                    ).replace("LIMIT 1)", "WHERE word_id = 1 LIMIT 1)")
                    if change == "segment"
                    else sql
                )
    repack(files, dist)
    report = run_validate(dist, "fixtures")
    assert any(message in f for f in report.failures), report.failures
