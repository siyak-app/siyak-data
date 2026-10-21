from pathlib import Path

import pytest

from pipeline import updates
from pipeline.sources import Source, SourceFile


def source(sha: str) -> Source:
    f = SourceFile("tafsir-book-7.json.gz", "https://example.invalid", "2026-10-20", sha)
    return Source(
        id="ar.x", name="x", homepage="h", license="l", attribution="a",
        path=Path("sources/tafsir/ar.x/source.toml"), files=(f,),
        extra={"quranpedia_book": 7},
    )  # fmt: skip


def fake(manifest_sha: str, rows: list[dict[str, object]]) -> object:
    def run(url: str) -> dict[str, object]:
        if url == updates.QURANPEDIA_MANIFEST:
            return {"files": [{"name": "tafsir-book-7.json.gz", "sha256": manifest_sha}]}
        assert url.endswith("since=2026-10-20")
        table = {"count": len(rows), "truncated": False, "rows": rows}
        return {"changes": {"ayah_book_contents": table, "books": {"rows": []}}}

    return run


def test_unchanged_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updates, "_json", fake("a" * 64, [{"book": 8, "surah": 1, "ayah": 1}]))
    [report] = updates.check_source(source("a" * 64))
    assert report.status == "unchanged"


def test_changed_dump_and_changes_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updates, "_json", fake("b" * 64, [{"book": 7, "surah": 2, "ayah": 3}]))
    [report] = updates.check_source(source("a" * 64))
    assert report.status == "changed"
    assert any("new file" in d for d in report.detail)
    assert any("1 ayah_book_contents change(s) since 2026-10-20 2:3" in d for d in report.detail)
