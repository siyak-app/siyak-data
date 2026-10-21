"""QUL tafsir databases on a small synthetic file (no third-party text)."""

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from pipeline.errors import PipelineError
from pipeline.qul import COLUMNS, load_qul
from pipeline.sources import Source, SourceFile

IDS = {(9, a): 1000 + a for a in range(1, 6)}
TEXT = '<div class=ar lang=ar><p>قوله تعالى: <span class="qpc-hafs">﴿نص﴾</span> شرح</p></div>'


def database(tmp_path: Path, rows: list[tuple[str, ...]]) -> Path:
    path = tmp_path / "qul.db"
    with sqlite3.connect(path) as conn:
        conn.execute(f"CREATE TABLE tafsir ({', '.join(c + ' TEXT' for c in COLUMNS)})")
        conn.executemany(f"INSERT INTO tafsir VALUES ({', '.join('?' * len(COLUMNS))})", rows)
    return path


def group(first: int, last: int, text: str = TEXT) -> list[tuple[str, ...]]:
    keys = ",".join(f"9:{a}" for a in range(first, last + 1))
    head = (f"9:{first}", f"9:{first}", f"9:{first}", f"9:{last}", keys, text)
    members = [
        (f"9:{a}", f"9:{first}", f"9:{first}", f"9:{last}", keys, "")
        for a in range(first + 1, last + 1)
    ]
    return [head, *members]


def test_groups_become_passages_and_empty_groups_are_gaps(tmp_path: Path) -> None:
    rows = group(1, 3) + group(4, 4, "<div class=ar lang=ar></div>") + group(5, 5)
    a = load_qul(database(tmp_path, rows), IDS)
    assert [(p.first, p.last) for p in a.passages] == [((9, 1), (9, 3)), ((9, 5), (9, 5))]
    assert a.gaps == [(9, 4)]
    assert a.accounting["source"] == a.accounting["stored"]


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([*group(1, 2)[:1], ("9:2", "9:1", "9:1", "9:2", "9:1,9:2", "نص")], "has its own text"),
        ([("9:1", "9:1", "9:1", "9:2", "9:1", TEXT)], "do not match"),
        ([("9:3", "9:3", "9:2", "9:3", "9:2,9:3", TEXT)], "not a range from this verse"),
        ([("9:2", "9:1", "9:1", "9:2", "9:1,9:2", "")], "outside its group"),
    ],
)
def test_bad_structure_fails(tmp_path: Path, rows: list[tuple[str, ...]], message: str) -> None:
    with pytest.raises(PipelineError, match=message):
        load_qul(database(tmp_path, rows), IDS)


def test_optional_source_is_skipped_until_cached_and_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIYAK_DATA_CACHE", str(tmp_path / "cache"))

    def source(sha: str) -> Source:
        f = SourceFile("x.zip", "https://example.invalid", "1", sha, manual=True)
        return Source(
            id="ar.x", name="x", homepage="h", license="l", attribution="a",
            path=tmp_path / "source.toml", files=(f,), extra={"optional": True},
        )  # fmt: skip

    assert source("a" * 64).skipped_optional()  # not in the cache
    pinned = source("a" * 64)
    pinned.cache_path("x.zip").parent.mkdir(parents=True, exist_ok=True)
    pinned.cache_path("x.zip").write_bytes(b"x")
    assert not pinned.skipped_optional()
    assert source("").skipped_optional()  # cached but not pinned
    assert not dataclasses.replace(source(""), extra={}).skipped_optional()
