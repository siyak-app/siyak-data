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


@pytest.mark.parametrize(
    ("tanzil", "qac", "rule"),
    [
        # E1: 2:164 لَـَٔايَـٰتٍ (1.1, hamza above a tatweel) vs لَءَايَٰتٍ (1.0.2)
        ("لَـَٔايَـٰتٍ",
         "لَءَايَٰتٍ", "E1"),
        # E2: small high yeh vs small yeh
        ("نِۧنَ", "نِۦنَ", "E2"),
        # E3: 12:39 tatweel + dagger alif vs alif maksura + dagger alif
        ("صَـٰحِبَ",
         "صَىٰحِبَ", "E3"),
    ],
)  # fmt: skip
def test_edition_rules(tanzil: str, qac: str, rule: str) -> None:
    assert compare(tanzil, qac) == "edition", rule


def test_edition_does_not_hide_letter_differences() -> None:
    # A real letter difference stays a failure even with the edition rules.
    assert (
        compare(
            "\u0645\u064e\u0644\u0650\u0643\u0650", "\u0645\u064e\u0627\u0644\u0650\u0643\u0650"
        )
        == "mismatch"
    )


def seg_of(surah: int, ayah: int, word: int, index: int, form: str) -> Segment:
    return Segment(surah, ayah, word, index, form, "N", ("STEM",), 0)


def test_merge_rule_pairs_two_tokens_with_one_qac_word() -> None:
    # 2:181 style: Tanzil 1.1 "بَعْدَ مَا" (two tokens), QAC "بَعْدَمَا" (one word).
    verses = {(2, 181): "مِنۢ بَعْدَ مَا"}
    qac = {
        (2, 181): [
            [seg_of(2, 181, 1, 1, "min[")],
            [seg_of(2, 181, 2, 1, "baEoda"), seg_of(2, 181, 2, 2, "maA")],
        ]
    }
    report = align(verses, qac)
    assert report.failures() == []
    (merged,) = report.merged()
    assert (merged.position, merged.level) == (2, "exact")
    words = report.aligned[(2, 181)]
    assert [w.position for w in words] == [1, 2]
    assert words[1].text_ar == "بَعْدَ مَا"
    assert " ".join(w.text_ar for w in words) == verses[(2, 181)]


def test_merge_rule_is_not_used_when_counts_match() -> None:
    verses = {(1, 1): "بَعْدَ مَا"}
    qac = {(1, 1): [[seg_of(1, 1, 1, 1, "baEoda")], [seg_of(1, 1, 2, 1, "maA")]]}
    report = align(verses, qac)
    assert report.merged() == []
    assert report.levels() == {"exact": 2}
