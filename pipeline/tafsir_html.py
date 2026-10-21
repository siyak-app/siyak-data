"""Tafsir text: Quranpedia HTML reduced to the tafsir subset (docs/pack-format.md §4.6).

A passage is split into paragraphs at block boundaries (``br``, ``p``, ``div``,
``hr``, headings, poems). Each paragraph is stored as HTML from this subset only:

    <b>…</b>                       emphasis (``strong``, headings)
    <span class="ayah">…</span>    a Quran quotation (``span.book-ayah``)
    <span class="ref">…</span>     a verse reference (``span.surah-ref``)
    <span class="poem">            a poem: lines separated by <br>, each line made
      <span class="hemistich">…</span>…<br>…    of hemistichs (``table.poem``)
    </span>

Only the markup changes: every character of text is kept, in order, except
the editor's footnotes when the pack drops them (``footnotes = "drop"``).
Whitespace runs become one space. Any tag not listed in ``_TAGS`` fails the
build, so nothing is dropped silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser

from pipeline.errors import PipelineError
from pipeline.normalize import normalize

Style = frozenset[str]
Run = tuple[str, Style]

#: How each source tag (``name`` or ``name.class``) is treated.
#: block: ends the paragraph; heading: its own paragraph in bold; inline: adds a
#: style (or none); footnote: editor's footnote (block or inline marker); poem
#: parts; break: line break (a paragraph break outside poems).
_TAGS: dict[str, tuple[str, str]] = {
    "br": ("break", ""),
    "hr": ("block", ""),
    "hr.hr-text": ("block", ""),
    "p": ("block", ""),
    "p.text-center": ("block", ""),
    "div": ("block", ""),
    "span.d-block": ("block", ""),
    "h3": ("heading", "b"),
    # Headings whose level the source wrote in Arabic-Indic digits (h3, h5).
    "h\u0663": ("heading", "b"),
    "h\u0665": ("heading", "b"),
    "strong": ("inline", "b"),
    "strong.masala": ("inline", "b"),
    "b": ("inline", "b"),
    "span.book-ayah text-primary": ("inline", "ayah"),
    "span.surah-ref": ("inline", "ref"),
    "span": ("inline", ""),
    "span.text-danger": ("inline", ""),
    "a.foot-note text-primary": ("footnote", "marker"),
    "div.foot-notes": ("footnote", "block"),
    "span.foot-note": ("footnote", "note"),
    "table.poem": ("poem", "table"),
    "tr": ("poem", "row"),
    "td": ("poem", "cell"),
}
_VOID = {"br", "hr"}
_WS = re.compile(r"\s+")


@dataclass
class Paragraph:
    """One paragraph: text runs, or poem lines of hemistichs; where it starts in print."""

    runs: list[Run] = field(default_factory=list)
    poem: list[list[list[Run]]] | None = None
    origin: tuple[str | None, int | None] = (None, None)

    def is_empty(self) -> bool:
        if self.poem is not None:
            return not any(text.strip() for line in self.poem for cell in line for text, _ in cell)
        return not any(text.strip() for text, _ in self.runs)


def _render_runs(runs: list[Run]) -> str:
    merged: list[Run] = []
    for text, style in runs:
        if merged and merged[-1][1] == style:
            merged[-1] = (merged[-1][0] + text, style)
        else:
            merged.append((text, style))
    out = []
    for text, style in merged:
        html = escape(text, quote=False)
        if "ayah" in style:
            html = f'<span class="ayah">{html}</span>'
        elif "ref" in style:
            html = f'<span class="ref">{html}</span>'
        if "b" in style:
            html = f"<b>{html}</b>"
        out.append(html)
    return "".join(out)


def _clean_runs(runs: list[Run]) -> list[Run]:
    """Collapse whitespace across runs and trim the ends; drop empty runs."""
    joined = "".join(text for text, _ in runs)
    target = _WS.sub(" ", joined).strip()
    out: list[Run] = []
    prev_space = True  # leading whitespace is dropped
    for text, style in runs:
        piece = []
        for ch in text:
            if not ch.isspace():
                prev_space = False
                piece.append(ch)
            elif not prev_space:
                prev_space = True
                piece.append(" ")
        if piece:
            out.append(("".join(piece), style))
    if out and out[-1][0].endswith(" "):
        text, style = out[-1]
        out[-1] = (text.rstrip(" "), style)
        if not out[-1][0]:
            out.pop()
    assert "".join(t for t, _ in out) == target
    return out


def render(paragraph: Paragraph) -> str:
    """The paragraph as subset HTML."""
    if paragraph.poem is None:
        return _render_runs(_clean_runs(paragraph.runs))
    lines = []
    for line in paragraph.poem:
        cells = [_render_runs(_clean_runs(cell)) for cell in line]
        cells = [c for c in cells if c]
        if cells:
            lines.append("".join(f'<span class="hemistich">{c}</span>' for c in cells))
    return '<span class="poem">' + "<br>".join(lines) + "</span>"


class _Converter(HTMLParser):
    def __init__(self, *, drop_footnotes: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.drop_footnotes = drop_footnotes
        self.paragraphs: list[Paragraph] = []
        self.current = Paragraph()
        self.styles: list[tuple[str, str, str]] = []  # open tags: (tag, style, kind)
        self.skip_depth = 0  # >0 while inside a dropped footnote
        self.skip_tag = ""
        self.dropped: list[str] = []
        self.origin: tuple[str | None, int | None] = (None, None)
        self.unknown: list[str] = []

    # paragraph handling
    def _style(self) -> Style:
        return frozenset(s for _, s, _ in self.styles if s)

    def flush(self) -> None:
        if not self.current.is_empty():
            self.paragraphs.append(self.current)
        self.current = Paragraph(origin=self.origin)

    def start_item(self, origin: tuple[str | None, int | None]) -> None:
        """A new page piece begins: a paragraph that is still open continues."""
        self.origin = origin
        if self.current.is_empty():
            self.current.origin = origin
        else:
            self._text(" ")

    def _text(self, data: str) -> None:
        if self.current.poem is not None:
            line = self.current.poem[-1] if self.current.poem else None
            if line is None:
                self.current.poem.append([[]])
                line = self.current.poem[-1]
            if not line:
                line.append([])
            line[-1].append((data, self._style()))
        else:
            self.current.runs.append((data, self._style()))

    # parser callbacks
    @staticmethod
    def _key(tag: str, attrs: list[tuple[str, str | None]]) -> str:
        cls = dict(attrs).get("class")
        return f"{tag}.{cls}" if cls else tag

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        key = self._key(tag, attrs)
        if self.skip_depth:
            self.skip_depth += tag == self.skip_tag
            return
        rule = _TAGS.get(key)
        if rule is None:
            self.unknown.append(key)
            return
        kind, arg = rule
        handler = {
            "footnote": self._footnote,
            "break": self._break,
            "block": self._block,
            "heading": self._block,
            "inline": self._inline,
            "poem": self._poem,
        }[kind]
        handler(tag, arg)

    def _footnote(self, tag: str, arg: str) -> None:
        if self.drop_footnotes:
            if tag not in _VOID:
                self.skip_depth, self.skip_tag = 1, tag
                self.dropped.append("")
            return
        if arg == "block":
            self.flush()
        if tag not in _VOID:
            self.styles.append((tag, "", "block" if arg == "block" else "inline"))

    def _break(self, _tag: str, _arg: str) -> None:
        if self.current.poem is not None:
            self._text(" ")
        else:
            self.flush()

    def _block(self, tag: str, arg: str) -> None:
        self.flush()
        if tag not in _VOID:
            self.styles.append((tag, arg, "block"))

    def _inline(self, tag: str, arg: str) -> None:
        self.styles.append((tag, arg, "inline"))

    def _poem(self, tag: str, arg: str) -> None:
        if arg == "table":
            self.flush()
            self.current.poem = []
        elif arg == "row" and self.current.poem is not None:
            self.current.poem.append([])
        elif arg == "cell" and self.current.poem is not None:
            if not self.current.poem:
                self.current.poem.append([])
            self.current.poem[-1].append([])
        self.styles.append((tag, "", "poem-table" if arg == "table" else "inline"))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            if tag == self.skip_tag:
                self.skip_depth -= 1
            return
        if tag in _VOID:
            return
        for i in range(len(self.styles) - 1, -1, -1):
            if self.styles[i][0] == tag:
                kind = self.styles[i][2]
                del self.styles[i:]
                break
        else:
            return  # a stray closing tag: nothing to close
        if kind == "poem-table" or (kind == "block" and self.current.poem is None):
            self.flush()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            self.dropped[-1] += data
            return
        self._text(data)


@dataclass
class Converted:
    """The paragraphs of a passage and the footnote text that was left out."""

    paragraphs: list[tuple[str, str | None, int | None]]
    dropped_footnotes: list[str]


def convert(pieces: list[tuple[str, str | None, int | None]], *, drop_footnotes: bool) -> Converted:
    """Convert a passage made of page pieces ``(html, part, page)`` into paragraphs."""
    conv = _Converter(drop_footnotes=drop_footnotes)
    for html, part, page in pieces:
        conv.start_item((part, page))
        conv.feed(html)
        conv.close()
        # Tags left open at the end of a page piece stay open into the next one.
    conv.flush()
    if conv.unknown:
        raise PipelineError(f"unknown HTML tag(s) in tafsir text: {sorted(set(conv.unknown))}")
    out = [(render(p), p.origin[0], p.origin[1]) for p in conv.paragraphs]
    return Converted([p for p in out if p[0]], conv.dropped)


_TAG = re.compile(r"<[^>]*>")
_FOOTNOTE_BLOCK = re.compile(r'<div class="foot-notes">.*?</div>', re.S)
_FOOTNOTE_MARK = re.compile(r"<a class=\"foot-note[^\"]*\"[^>]*>.*?</a>", re.S)


def letters(text: str) -> str:
    """Every non-whitespace character, in order: the measure of 'text unchanged'."""
    return _WS.sub("", text)


def source_letters(html: str, *, drop_footnotes: bool) -> str:
    """Independent of the converter: the text of source HTML, footnotes removed by pattern."""
    if drop_footnotes:
        html = _FOOTNOTE_MARK.sub("", _FOOTNOTE_BLOCK.sub("", html))
    return letters(unescape(_TAG.sub("", html)))


def subset_letters(html: str) -> str:
    """The text of a stored paragraph."""
    return letters(unescape(_TAG.sub("", html)))


_ARABIC_LETTERS = re.compile(r"[^ء-ي]")


def skeleton(text_or_html: str) -> str:
    """Arabic letters only, after the search normalization: compares two digital editions."""
    return _ARABIC_LETTERS.sub("", normalize(unescape(_TAG.sub(" ", text_or_html))))
