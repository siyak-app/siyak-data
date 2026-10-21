import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest

from pipeline.build import run_build
from pipeline.normalize import normalize
from pipeline.validate import run_validate


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixture_build_passes_all_gates(built_fixtures: Path, fixture_sources: None) -> None:
    report = run_validate(built_fixtures, "fixtures")
    assert report.failures == []


def test_build_is_reproducible(fixtures_profile: Path) -> None:
    first = {p.name: sha(p) for p in run_build()}
    second = {p.name: sha(p) for p in run_build()}
    assert first == second
    assert set(first) == {"core.db", "en.pickthall.sqlite"}


def test_core_contents(built_fixtures: Path) -> None:
    conn = sqlite3.connect(built_fixtures / "core.db")
    assert conn.execute("SELECT count(*) FROM surahs").fetchone() == (114,)
    row = conn.execute(
        "SELECT name_ar, name_tr, name_en, revelation_type, bismillah IS NOT NULL "
        "FROM surahs WHERE number = 112"
    ).fetchone()
    assert row == ("الإخلاص", "İhlâs", "Al-Ikhlaas", "meccan", 1)
    verse = conn.execute(
        "SELECT id, juz, text_uthmani, text_clean FROM verses WHERE surah = 112 AND ayah = 1"
    ).fetchone()
    assert verse[:2] == (6222, 30)
    assert normalize(verse[2]) == "قل هو الله احد"
    assert verse[3] == "قل هو الله أحد"
    assert conn.execute("SELECT text_norm FROM verses_fts WHERE rowid = 6222").fetchone() == (
        "قل هو الله احد",
    )
    hits = conn.execute("SELECT rowid FROM verses_fts WHERE verses_fts MATCH 'احد'").fetchall()
    assert (6222,) in hits
    assert conn.execute(
        "SELECT text FROM translations WHERE pack_id = 'en.pickthall' AND verse_id = 6222"
    ).fetchone() == ("Say: He is Allah, the One!",)
    notices = {r[0] for r in conn.execute("SELECT id FROM notices")}
    assert {"tanzil.text.uthmani", "tanzil.text.simple-clean", "en.pickthall"} <= notices


def tampered(built: Path, tmp_path: Path, sql: str) -> Path:
    dist = tmp_path / "tampered"
    shutil.copytree(built, dist)
    with sqlite3.connect(dist / "core.db") as conn:
        conn.execute(sql)
    return dist


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("DELETE FROM verses WHERE surah = 112 AND ayah = 3", "surah 112: ayahs not contiguous"),
        (
            "UPDATE verses SET text_clean = text_uthmani WHERE id = 6222",
            "112:1: text_clean contains",
        ),
        ("UPDATE verses SET text_uthmani = ' ' WHERE id = 6222", "112:1: empty text_uthmani"),
        ("UPDATE verses SET juz = 31 WHERE id = 6222", "112:1: juz 31 outside 1..30"),
        (
            "UPDATE surahs SET bismillah = NULL WHERE number = 112",
            "surah 112: bismillah is missing",
        ),
        ("UPDATE surahs SET name_tr = '' WHERE number = 5", "surah 5: empty name_tr"),
        ("DELETE FROM translations WHERE verse_id = 6222", "core.db translations en.pickthall"),
        ("DELETE FROM notices WHERE id = 'tanzil.text.uthmani'", "'tanzil.text.uthmani' missing"),
    ],
)
def test_gates_name_the_problem(
    built_fixtures: Path, fixture_sources: None, tmp_path: Path, sql: str, message: str
) -> None:
    report = run_validate(tampered(built_fixtures, tmp_path, sql), "fixtures")
    assert any(message in failure for failure in report.failures), report.failures


def test_gate_catches_missing_translation_row(
    built_fixtures: Path, fixture_sources: None, tmp_path: Path
) -> None:
    dist = tmp_path / "tampered"
    shutil.copytree(built_fixtures, dist)
    with sqlite3.connect(dist / "en.pickthall.sqlite") as conn:
        conn.execute("DELETE FROM translations WHERE verse_id = 6222")
    report = run_validate(dist, "fixtures")
    assert any("en.pickthall.sqlite: missing verse ids, first [6222]" in f for f in report.failures)
