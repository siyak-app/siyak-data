"""Passage assembly on small synthetic dumps (no third-party text)."""

import pytest

from pipeline.errors import PipelineError
from pipeline.quranpedia import Dump, Piece, Rules, assemble, parse_rules

# Synthetic commentary: long enough (30+ letters) to be verified as a copy.
T1 = "شَرْحُ الْآيَةِ الْأُولَى فِي هَذَا الْكِتَابِ بِكَلَامٍ طَوِيلٍ مُفَصَّلٍ"
T2 = "شرح الآية الثانية في هذا الكتاب بكلام آخر طويل مفصل جدا"
T3 = "شرح الآية الثالثة في هذا الكتاب بكلام ثالث طويل مفصل كذلك"
REP = "<span class='d-block'>نص مكرر لاشتراكه مع الآية ١:</span><span>{}</span>"
REL = "<h٥>جزء ذو علاقة من تفسير الآية السابقة:</h٥><span>{}</span>"
VERSES = {(9, a): f"كلمة{a} ثانية ثالثة رابعة خامسة" for a in range(1, 6)}
RULES = Rules(book=1, drop_footnotes=True)


def paged(text: str, page: int) -> Piece:
    return Piece(text, "1", page)


def unpaged(text: str) -> Piece:
    return Piece(text, None, None)


def spans(assembly: object) -> list[tuple[int, int]]:
    return [(p.first[1], p.last[1]) for p in assembly.passages]  # type: ignore[attr-defined]


def run(entries: dict[tuple[int, int], list[Piece]], rules: Rules = RULES) -> object:
    return assemble(Dump({"id": 1}, entries), rules, VERSES)


def test_verified_repeated_copy_joins_the_named_verse() -> None:
    a = run({(9, 1): [paged(T1, 10)], (9, 2): [paged(T2, 11), unpaged(REP.format(T1))]})
    assert spans(a) == [(1, 2)]
    assert a.copies["rep verified"] == 1
    stored = "".join(s.html for s in a.passages[0].sections)
    assert "نص مكرر" not in stored and stored.count("الأولى") + stored.count("الْأُولَى") == 1


def test_unverified_copy_stays_with_its_label() -> None:
    a = run({(9, 1): [paged(T1, 10)], (9, 2): [paged(T2, 11), unpaged(REP.format(T3))]})
    assert spans(a) == [(1, 1), (2, 2)]
    assert a.copies["rep unverified"] == 1
    assert "نص مكرر" in "".join(s.html for s in a.passages[1].sections)


def test_related_part_is_verified_against_an_earlier_verse() -> None:
    a = run({(9, 1): [paged(T1, 10)], (9, 2): [paged(T2, 11)], (9, 3): [unpaged(REL.format(T1))]})
    assert spans(a) == [(1, 3)]
    assert a.copies["rel verified"] == 1


def test_unpaged_repeat_of_the_same_verse_is_dropped_without_linking() -> None:
    a = run({(9, 1): [paged(T1, 10)], (9, 2): [paged(T2, 11), unpaged(T2.replace(" ", "  "))]})
    assert spans(a) == [(1, 1), (2, 2)]
    assert a.copies["unpaged duplicate"] == 1


def test_identical_refrain_does_not_join_verses_with_their_own_text() -> None:
    refrain = paged("فبأي آلاء ربكما تكذبان", 20)
    a = run(
        {
            (9, 1): [refrain],
            (9, 2): [paged(T2, 21)],
            (9, 3): [refrain],
            (9, 4): [refrain],
        }
    )
    assert spans(a) == [(1, 1), (2, 2), (3, 4)]


def test_gap_joins_the_previous_passage_only_if_it_is_quoted() -> None:
    quoting = paged(T1 + " قوله " + VERSES[(9, 2)], 10)
    a = run({(9, 1): [quoting], (9, 3): [paged(T3, 12)]})
    assert spans(a) == [(1, 2), (3, 3)]
    assert (9, 2) in a.gap_merged
    assert (9, 4) in a.gaps and (9, 5) in a.gaps


def test_exclusion_and_move_rules() -> None:
    rules = parse_rules(
        {
            "quranpedia_book": 1,
            "exclude": [{"part": "0", "reason": "editor"}],
            "introduction": [{"verse": "9:3", "part": "1", "pages": [1, 2], "reason": "intro"}],
        },
        "test",
    )
    entries = {
        (1, 1): [paged(T1, 10)],
        (9, 3): [Piece("مقدمة المحقق", "0", 5), paged("مقدمة المؤلف", 1), paged(T3, 30)],
    }
    a = run(entries, rules)
    assert a.introduction is not None and a.introduction.kind == "introduction"
    assert (a.introduction.first, a.introduction.last) == ((1, 1), (1, 1))
    assert [s.html for s in a.introduction.sections] == ["مقدمة المؤلف"]
    assert [s.html for s in a.passages[0].sections] == [T1]
    assert a.excluded == {"editor": len("مقدمةالمحقق")}
    assert a.moved == {"intro": len("مقدمةالمؤلف")}


def test_rule_matching_nothing_fails() -> None:
    rules = parse_rules({"quranpedia_book": 1, "exclude": [{"part": "9", "reason": "x"}]}, "test")
    with pytest.raises(PipelineError, match="matches nothing"):
        run({(9, 1): [paged(T1, 10)]}, rules)


def test_from_text_cuts_the_end_of_a_piece() -> None:
    rules = parse_rules(
        {"quranpedia_book": 1, "exclude": [{"from_text": "تم طبع", "reason": "printer"}]}, "test"
    )
    a = run({(9, 1): [paged(T1 + "<br>تم طبع الكتاب", 10)]}, rules)
    assert [s.html for s in a.passages[0].sections] == [T1]
    assert a.excluded == {"printer": len("<br>تمطبعالكتاب") - len("<br>")}


def test_every_letter_is_accounted_for() -> None:
    a = run(
        {
            (9, 1): [paged(T1 + '<div class="foot-notes">(١) حاشية</div>', 10)],
            (9, 2): [paged(T2, 11), unpaged(REP.format(T1))],
        }
    )
    acc = a.accounting
    assert acc["footnotes"] == len("(١)حاشية")
    assert acc["source"] == sum(v for k, v in acc.items() if k != "source")


def test_unpaged_duplicates_can_be_kept() -> None:
    rules = Rules(book=1, drop_footnotes=True, dedupe_unpaged=False)
    a = run({(9, 1): [paged(T1, 10), unpaged(T1.replace(" ", "  "))]}, rules)
    assert a.copies["unpaged kept"] == 1 and "unpaged duplicate" not in a.copies


def test_edition_headings_draw_the_passages() -> None:
    heading = "[سورة التوبة (٩) : الآيات ١ الى ٢]"
    rules = Rules(book=1, drop_footnotes=True, passage_headings=True)
    entries = {
        (9, 1): [paged(heading + T1, 10)],
        (9, 2): [paged(T2, 11)],
        (9, 3): [paged("[سورة التوبة (٩) : آية ٣]" + T3, 12), unpaged(REL.format(T1))],
    }
    plain = run(entries)
    assert spans(plain) == [(1, 3)]  # the related part joins 3 to 1
    a = run(entries, rules)
    assert spans(a) == [(1, 2), (3, 3)]
    assert a.headings["headings"] == 2 and a.headings["passages_changed"] == 2
