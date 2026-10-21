import pytest

from pipeline.errors import PipelineError
from pipeline.tafsir_html import convert, source_letters, subset_letters


def paragraphs(html: str, *, drop: bool = True) -> list[str]:
    return [p[0] for p in convert([(html, "1", 5)], drop_footnotes=drop).paragraphs]


def test_inline_styles_become_the_subset() -> None:
    html = (
        'قال <span class="book-ayah text-primary">﴿آية﴾</span> و<strong>مسألة</strong> '
        '<span class="surah-ref">[البقرة: ٢]</span> <span class="text-danger">نص</span>'
    )
    assert paragraphs(html) == [
        'قال <span class="ayah">﴿آية﴾</span> و<b>مسألة</b> <span class="ref">[البقرة: ٢]</span> نص'
    ]


def test_blocks_and_breaks_split_paragraphs_and_headings_are_bold() -> None:
    html = '<h3>عنوان</h3>أول<br />\r ثان<p class="text-center">وسط</p><hr>آخر'
    assert paragraphs(html) == ["<b>عنوان</b>", "أول", "ثان", "وسط", "آخر"]


def test_footnotes_are_dropped_or_kept() -> None:
    html = (
        'نص<a class="foot-note text-primary" href="#f-1">(١)</a> تام'
        '<div class="foot-notes">(١) حاشية المحقق.</div>'
    )
    assert paragraphs(html) == ["نص تام"]
    assert paragraphs(html, drop=False) == ["نص(١) تام", "(١) حاشية المحقق."]
    assert convert([(html, None, None)], drop_footnotes=True).dropped_footnotes == [
        "(١)",
        "(١) حاشية المحقق.",
    ]


def test_poem_table_becomes_lines_of_hemistichs() -> None:
    html = (
        "قال الشاعر:<table class='poem'><tr><td>صدر أول</td><td>عجز أول</td></tr>"
        "<tr><td>صدر ثان</td><td>عجز ثان</td></tr></table>ثم"
    )
    assert paragraphs(html) == [
        "قال الشاعر:",
        '<span class="poem"><span class="hemistich">صدر أول</span><span class="hemistich">'
        'عجز أول</span><br><span class="hemistich">صدر ثان</span><span class="hemistich">'
        "عجز ثان</span></span>",
        "ثم",
    ]


def test_a_paragraph_continues_over_a_page_break_and_keeps_its_first_page() -> None:
    converted = convert(
        [("بداية الجملة", "2", 10), ("وتمامها<br>جديد", "2", 11)], drop_footnotes=True
    )
    assert converted.paragraphs == [("بداية الجملة وتمامها", "2", 10), ("جديد", "2", 11)]


def test_text_is_escaped_and_whitespace_collapsed() -> None:
    assert paragraphs("  أ   &amp;  <b>ب</b>\n\n ج  ") == ["أ &amp; <b>ب</b> ج"]


def test_unknown_tag_fails() -> None:
    with pytest.raises(PipelineError, match="unknown HTML tag"):
        paragraphs('<span class="new">x</span>')


@pytest.mark.parametrize(
    "html",
    [
        'أ<span class="book-ayah text-primary">﴿ب﴾</span><br />ج',
        "<div class=\"foot-notes\"><span class='foot-note' id='f'>١ حاشية</span><br></div>د",
        "<table class='poem'><tr><td>هـ</td><td>و</td></tr></table>",
        "<span class='d-block'>ز</span><span>ح"
        '<a class="foot-note text-primary" href="#">(٢)</a></span>',
    ],
)
def test_letters_are_unchanged(html: str) -> None:
    got = "".join(subset_letters(p) for p in paragraphs(html))
    assert got == source_letters(html, drop_footnotes=True)
