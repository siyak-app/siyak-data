import sqlite3
from pathlib import Path

import pytest

from pipeline.schema import (
    SCHEMA_VERSION,
    PackInfo,
    apply_content_schema,
    build_timestamp,
    new_database,
    read_pack_info,
    write_pack_info,
)

EXPECTED_TABLES = {
    "surahs",
    "verses",
    "packs",
    "translations",
    "notices",
    "content_meta",
    "tafsir",
    "tafsir_paragraphs",
    "words",
    "roots",
    "lemmas",
    "word_segments",
    "verses_fts",
    "translations_fts",
}


def test_content_schema_creates_all_tables() -> None:
    conn = sqlite3.connect(":memory:")
    apply_content_schema(conn)
    names = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not r[0].startswith(("verses_fts_", "translations_fts_"))
    }
    assert names == EXPECTED_TABLES
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_pack_info_round_trip(tmp_path: Path) -> None:
    info = PackInfo("en.x", "translation", "1.0.0", 1, "2026-01-01T00:00:00Z", "v1")
    conn = new_database(tmp_path / "p.sqlite")
    write_pack_info(conn, info)
    assert read_pack_info(conn) == info


def test_pack_info_rejects_multiple_rows() -> None:
    conn = sqlite3.connect(":memory:")
    info = PackInfo("en.x", "translation", "1.0.0", 1, "t", "v")
    write_pack_info(conn, info)
    conn.execute("INSERT INTO pack_info SELECT * FROM pack_info")
    with pytest.raises(ValueError, match="exactly one row"):
        read_pack_info(conn)


def test_build_timestamp_honours_source_date_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    assert build_timestamp() == "2026-01-01T00:00:00Z"
