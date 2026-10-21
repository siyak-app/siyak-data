"""The fixtures are verbatim excerpts of the pinned files and stay in sync with them."""

import gzip
import json
from pathlib import Path

import pytest

from pipeline.tanzil import parse_quran_xml, parse_translation

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
CACHE = ROOT / ".cache"


FIXTURE_HEADER_LINES = 4  # three "# FIXTURE COPY …" comment lines and a blank line


@pytest.mark.parametrize(
    "rel", ["tanzil", "translations/en.pickthall", "tafsir/ar.jalalayn", "tafsir/ar.razi"]
)
def test_fixture_source_toml_differs_only_in_hashes(rel: str) -> None:
    real = (ROOT / "sources" / rel / "source.toml").read_text(encoding="utf-8").splitlines()
    fixture = (FIXTURES / "sources" / rel / "source.toml").read_text(encoding="utf-8")
    lines = fixture.splitlines()
    assert lines[0].startswith("# FIXTURE COPY")
    body = lines[FIXTURE_HEADER_LINES:]
    assert len(body) == len(real)
    for a, b in zip(real, body, strict=True):
        if a != b:
            assert a.startswith("sha256 = ")
            assert b.startswith("sha256 = ")


@pytest.mark.parametrize("rel", ["tanzil/NOTICE", "translations/en.pickthall/NOTICE"])
def test_fixture_notices_are_copies(rel: str) -> None:
    assert (FIXTURES / "sources" / rel).read_bytes() == (ROOT / "sources" / rel).read_bytes()


@pytest.mark.full
@pytest.mark.parametrize("name", ["quran-uthmani.xml", "quran-simple-clean.xml"])
def test_fixture_verses_are_identical_to_pinned_text(name: str) -> None:
    pinned = CACHE / "tanzil" / name
    if not pinned.exists():
        pytest.skip("pinned Tanzil text not in .cache/")
    full = {(a.surah, a.ayah): a for a in parse_quran_xml(pinned).verses}
    excerpt = parse_quran_xml(FIXTURES / "cache" / "tanzil" / name)
    assert excerpt.notice == parse_quran_xml(pinned).notice
    assert excerpt.verses
    for aya in excerpt.verses:
        assert full[(aya.surah, aya.ayah)] == aya


@pytest.mark.full
def test_fixture_translation_is_identical_to_pinned_text() -> None:
    pinned = CACHE / "en.pickthall" / "en.pickthall.txt"
    if not pinned.exists():
        pytest.skip("pinned translation not in .cache/")
    full = parse_translation(pinned)
    excerpt = parse_translation(FIXTURES / "cache" / "en.pickthall" / "en.pickthall.txt")
    assert excerpt.header == full.header
    assert all(full.verses[k] == v for k, v in excerpt.verses.items())


@pytest.mark.full
@pytest.mark.parametrize(
    ("pack_id", "name"),
    [("ar.jalalayn", "tafsir-book-272.json.gz"), ("ar.razi", "tafsir-book-352.json.gz")],
)
def test_tafsir_excerpts_are_identical_to_pinned_dump(pack_id: str, name: str) -> None:
    pinned = CACHE / pack_id / name
    if not pinned.exists():
        pytest.skip("pinned dump not in .cache/")
    full = json.loads(gzip.decompress(pinned.read_bytes()))
    excerpt = json.loads(gzip.decompress((FIXTURES / "cache" / pack_id / name).read_bytes()))
    assert {k: v for k, v in excerpt.items() if k != "ayahs"} == {
        k: v for k, v in full.items() if k != "ayahs"
    }
    entries = {(e["surah"], e["ayah"]): e for e in full["ayahs"]}
    assert excerpt["ayahs"]
    for entry in excerpt["ayahs"]:
        assert entries[(entry["surah"], entry["ayah"])] == entry
    surahs = {e["surah"] for e in excerpt["ayahs"]}
    assert len(excerpt["ayahs"]) == sum(1 for e in full["ayahs"] if e["surah"] in surahs)
