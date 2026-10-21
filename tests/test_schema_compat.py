"""Every built pack installs into a database created from the content schema.

By default the schema is schema/content.sql. When SIYAK_CONTENT_MIGRATIONS
points at the app's src-tauri/migrations/content/ directory (CI job
"schema-compat"), the app's ordered migrations are applied instead.
"""

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from pipeline.build import morphology_sources, translation_sources
from pipeline.build_translation import packs_row
from pipeline.compress import decompress_pack, frame_content_size
from pipeline.errors import PipelineError
from pipeline.install import install_archive_pack, install_pack
from pipeline.schema import SCHEMA_VERSION, apply_content_schema, schema_shape
from pipeline.sources import load_all
from pipeline.validate import install_into_core_copy


def migrations() -> list[str] | None:
    directory = os.environ.get("SIYAK_CONTENT_MIGRATIONS")
    if not directory:
        return None
    files = sorted(Path(directory).glob("*.sql"))
    assert files, f"no *.sql migrations in {directory}"
    return [f.read_text(encoding="utf-8") for f in files]


def test_every_pack_installs(built_fixtures: Path, fixture_sources: None, tmp_path: Path) -> None:
    # Install what users download: decompress each published .sqlite.zst first.
    sources = translation_sources(load_all())
    packs = [
        (
            decompress_pack(
                built_fixtures / f"{s.pack.id}.sqlite.zst",
                tmp_path / f"{s.pack.id}.sqlite",
                max_size=(built_fixtures / f"{s.pack.id}.sqlite").stat().st_size,
            ),
            s,
        )
        for s in sources
        if s.pack
    ]
    assert packs
    conn = install_into_core_copy(built_fixtures / "core.db", packs, migrations())
    verses = conn.execute("SELECT count(*) FROM verses").fetchone()[0]
    for path, source in packs:
        assert source.pack is not None
        count = conn.execute(
            "SELECT count(*) FROM translations WHERE pack_id = ?", (source.pack.id,)
        ).fetchone()[0]
        assert count == verses, path.name
        hits = conn.execute(
            "SELECT count(*) FROM translations_fts WHERE translations_fts MATCH 'Allah' "
            "AND pack_id = ?",
            (source.pack.id,),
        ).fetchone()[0]
        assert hits > 0
    # Reinstalling replaces rows instead of duplicating them.
    path, source = packs[0]
    install_pack(conn, path, packs_row(source, installed_at="again", bundled=False))
    assert conn.execute("SELECT count(*) FROM translations").fetchone()[0] == verses


def test_core_db_matches_the_schema(built_fixtures: Path) -> None:
    fresh = sqlite3.connect(":memory:")
    scripts = migrations()
    if scripts is None:
        apply_content_schema(fresh)
    else:
        for script in scripts:
            fresh.executescript(script)
    core = sqlite3.connect(built_fixtures / "core.db")
    core_shape, fresh_shape = schema_shape(core), schema_shape(fresh)
    keys = set(core_shape) | set(fresh_shape)
    assert sorted(k for k in keys if core_shape.get(k) != fresh_shape.get(k)) == []
    # The app's runner sets user_version to the number of applied migrations.
    expected_version = SCHEMA_VERSION if scripts is None else len(scripts)
    assert core.execute("PRAGMA user_version").fetchone() == (expected_version,)


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("CREATE TRIGGER t AFTER INSERT ON translations BEGIN SELECT 1; END", "trigger"),
        ("CREATE VIEW v AS SELECT 1", "view"),
        ("CREATE TABLE extra (x)", "unexpected table 'extra'"),
        ("UPDATE pack_info SET id = 'en.other'", "pack_info says en.other"),
        ("UPDATE pack_info SET schema_version = 99", "schema_version 99"),
    ],
)
def test_untrusted_pack_is_rejected(
    built_fixtures: Path, fixture_sources: None, tmp_path: Path, sql: str, message: str
) -> None:
    source = translation_sources(load_all())[0]
    assert source.pack is not None
    bad = tmp_path / "bad.sqlite"
    shutil.copyfile(built_fixtures / f"{source.pack.id}.sqlite", bad)
    with sqlite3.connect(bad) as conn:
        conn.execute(sql)
    with pytest.raises(PipelineError, match=message):
        install_into_core_copy(built_fixtures / "core.db", [(bad, source)])


def test_morphology_pack_installs(
    built_fixtures: Path, fixture_sources: None, tmp_path: Path
) -> None:
    # Install what users download: unpack the published .tar.zst archive first.
    (source,) = morphology_sources(load_all())
    assert source.pack is not None
    archive = built_fixtures / f"{source.pack.id}.tar.zst"
    conn = install_into_core_copy(built_fixtures / "core.db", [], migrations())
    row = packs_row(source, installed_at="test", bundled=False)
    files = install_archive_pack(conn, archive, row, tmp_path, frame_content_size(archive))
    assert "qac/NOTICE" in files
    segments = conn.execute("SELECT count(*) FROM word_segments").fetchone()[0]
    assert segments > 0
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
