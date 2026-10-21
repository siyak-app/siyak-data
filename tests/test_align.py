from pathlib import Path

import pytest

from pipeline.align import align, compare, group_words, is_mark_token, tanzil_words
from pipeline.errors import PipelineError
from pipeline.qac import Segment, parse_qac
from pipeline.tanzil import parse_quran_xml

FIXTURES = Path(__file__).parent / "fixtures" / "cache"
CACHE = Path(__file__).parent.parent / ".cache"
PAUSE = "ۛ"  # small high three dots
SAJDAH = "۩"


def test_mark_tokens_attach_to_the_previous_word() -> None:
    text = f"ذَلِكَ {PAUSE} فِيهِ {SAJDAH}"
    words = tanzil_words(text, "t")
    assert [w.position for w in words] == [1, 2]
    assert words[0].token == "ذَلِكَ"
    assert words[0].text_ar == f"ذَلِكَ {PAUSE}"
    assert words[1].text_ar.endswith(f" {SAJDAH}")
    assert " ".join(w.text_ar for w in words) == text
    assert is_mark_token(PAUSE + PAUSE)
    assert not is_mark_token("ف" + PAUSE)


@pytest.mark.parametrize("text", [f"{PAUSE} ف", "ف  ق"])
def test_bad_verse_layout_fails(text: str) -> None:
    with pytest.raises(PipelineError):
        tanzil_words(text, "t")


@pytest.mark.parametrize(
    ("tanzil", "qac", "level"),
    [
        ("مَـٰلِكِ", "مَـٰلِكِ", "exact"),
        ("مَـٰلِكِ", "مَٰلِكِ", "canonical"),
        ("رَبِّ", "رَبِّ", "canonical"),
        ("الصَّلَوٰةَ", "الصلوة", "skeleton"),
        ("ملك", "مالك", "mismatch"),
    ],
)  # fmt: skip
def test_compare_levels(tanzil: str, qac: str, level: str) -> None:
    assert compare(tanzil, qac) == level


def test_out_of_order_segments_fail() -> None:
    rows = [
        Segment(1, 1, 1, 1, "bi", "P", ("PREFIX",), 1),
        Segment(1, 1, 1, 3, "x", "N", ("STEM",), 2),
    ]
    with pytest.raises(PipelineError, match="out of order"):
        group_words(rows)


def fixture_alignment() -> tuple[
    dict[tuple[int, int], str], dict[tuple[int, int], list[list[Segment]]]
]:
    verses = {
        (a.surah, a.ayah): a.text
        for a in parse_quran_xml(FIXTURES / "tanzil" / "quran-uthmani.xml").verses
    }
    qac_file = FIXTURES / "morphology.qac" / "quranic-corpus-morphology-0.4.txt"
    return verses, group_words(parse_qac(qac_file).segments)


def test_synthetic_fixture_aligns() -> None:
    verses, qac = fixture_alignment()
    report = align(verses, qac)
    assert report.failures() == []
    assert report.levels()["canonical"] > 0  # tatweel dropped in the synthetic forms


def test_word_count_mismatch_is_reported() -> None:
    verses, qac = fixture_alignment()
    qac[(112, 1)] = qac[(112, 1)][:-1]
    report = align(verses, qac)
    assert report.count_mismatches == [(112, 1, 4, 3)]
    assert report.failures() == ["112:1: Tanzil has 4 words, QAC has 3"]
