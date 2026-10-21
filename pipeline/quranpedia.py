"""Quranpedia tafsir dumps → passages (spec §5.2, §6.6; docs/pack-format.md §4.6).

A dump has one entry per verse; an entry is a list of *pieces* of printed pages
(``part``/``page``). This module turns them into passages (verse ranges with
their pieces), in this order:

1. **Edition matter** listed in ``[[build.exclude]]`` (editor or publisher
   introductions, studies, indexes, printer colophons) is left out.
2. **The author's introduction**, where the dump attaches it to another verse,
   is moved to the start of 1:1 (``[[build.move_to_start]]``).
3. **Quranpedia's copy labels** ("نص مكرر لاشتراكه مع الآية N:", "جزء ذو علاقة
   من تفسير الآية السابقة:") start a section holding a copy of another verse's
   text. When the copy is verified (its letters, compared with the search
   normalization, occur in the text stored for that verse), the label and the
   copy are not stored again and the two verses join one passage. Unverified
   sections stay as they are, label included.
4. **Duplicates from a second digital edition**: a piece without a page that
   is verified to repeat the paged text of a verse is treated the same way.
5. **Grouping**: verses sharing a piece, or joined by step 3/4, form one
   passage covering the whole range between them (spec §5.2).
6. **Gap merge** (M1c decision K4): a verse without text joins the preceding
   passage of the same surah only if that passage quotes the verse's first
   words. Other gaps stay empty and are reported.

The text of the pieces is never changed: steps 1–4 only leave out whole pieces
or sections (or, with ``from_text``, the end of a piece), and every left-out
character is counted (``Assembly.accounting``).
"""

from __future__ import annotations

import gzip
import itertools
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.errors import PipelineError
from pipeline.normalize import normalize
from pipeline.tafsir_html import skeleton, source_letters

Key = tuple[int, int]

_REP = re.compile(
    r"<span class=['\"]d-block['\"]>\s*نص مكرر لاشتراكه مع الآية"
    r"\s*([\u0660-\u06690-9]+)\s*:\s*</span>"
)
_REL = re.compile(r"<h\u0665>\s*جزء ذو علاقة من تفسير الآية السابقة\s*:?\s*</h\u0665>")
_DIGITS = str.maketrans("".join(chr(0x0660 + d) for d in range(10)), "0123456789")
#: A copy shorter than this (in letters) is too short to verify.
MIN_COPY_LETTERS = 30
#: Words of a verse that a passage must quote to absorb that verse (K4).
GAP_WORDS = 4
#: ...and that quotation must have at least this many letters.
MIN_GAP_PROBE = 6
_PAGE_ARTIFACT = re.compile(r"^[\d\u0660-\u0669]+-?$")


@dataclass(frozen=True)
class Piece:
    """A piece of a printed page as stored under one verse."""

    html: str
    part: str | None
    page: int | None

    @property
    def paged(self) -> bool:
        return self.page is not None


@dataclass(frozen=True)
class Section:
    """A piece, or the part of a piece that follows a copy label.

    Two sections are the same when their text, page and label are, even if they
    come from different pieces (the same copy repeated under several verses).
    """

    piece: Piece = field(compare=False)
    html: str
    part: str | None
    page: int | None
    label: str = ""  # "", "rep" or "rel"
    target: int | None = None  # rep: the verse number the label names


@dataclass(frozen=True)
class PageRule:
    """A ``[[build.exclude]]`` or ``[[build.move_to_start]]`` entry."""

    reason: str
    part: str | None = None
    pages: tuple[int, int] | None = None
    verses: tuple[Key, Key] | None = None
    from_text: str = ""

    def matches(self, key: Key, piece: Piece) -> bool:
        if self.verses is not None and not self.verses[0] <= key <= self.verses[1]:
            return False
        if self.part is not None and piece.part != self.part:
            return False
        if self.pages is not None and not (
            piece.page is not None and self.pages[0] <= piece.page <= self.pages[1]
        ):
            return False
        return not self.from_text or self.from_text in piece.html


@dataclass(frozen=True)
class Rules:
    """The ``[build]`` table of a Quranpedia tafsir source."""

    book: int
    drop_footnotes: bool
    exclude: tuple[PageRule, ...] = ()
    move_to_start: tuple[PageRule, ...] = ()


def _key(text: str, where: str) -> Key:
    m = re.fullmatch(r"(\d+):(\d+)", text.strip())
    if not m:
        raise PipelineError(f"{where}: '{text}' is not a verse key 'surah:ayah'")
    return int(m.group(1)), int(m.group(2))


def _page_rule(raw: dict[str, Any], where: str, *, verse_required: bool) -> PageRule:
    reason = str(raw.get("reason", "")).strip()
    if not reason:
        raise PipelineError(f"{where}: every rule needs a 'reason'")
    verses = None
    if "verse" in raw:
        a, _, b = str(raw["verse"]).partition("-")
        verses = (_key(a, where), _key(b or a, where))
    elif verse_required:
        raise PipelineError(f"{where}: 'verse' is required")
    pages = raw.get("pages")
    if pages is not None and (len(pages) != 2 or pages[0] > pages[1]):
        raise PipelineError(f"{where}: 'pages' must be [first, last]")
    part = raw.get("part")
    return PageRule(
        reason=reason,
        part=None if part is None else str(part),
        pages=None if pages is None else (int(pages[0]), int(pages[1])),
        verses=verses,
        from_text=str(raw.get("from_text", "")),
    )


def parse_rules(build: dict[str, Any], where: str) -> Rules:
    """Read and check a source's ``[build]`` table."""
    book = build.get("quranpedia_book")
    if not isinstance(book, int):
        raise PipelineError(f"{where} [build]: 'quranpedia_book' must be an integer")
    footnotes = build.get("footnotes", "drop")
    if footnotes not in ("drop", "keep"):
        raise PipelineError(f"{where} [build]: footnotes must be 'drop' or 'keep'")
    return Rules(
        book=book,
        drop_footnotes=footnotes == "drop",
        exclude=tuple(
            _page_rule(r, f"{where} [[build.exclude]]", verse_required=False)
            for r in build.get("exclude", [])
        ),
        move_to_start=tuple(
            _page_rule(r, f"{where} [[build.move_to_start]]", verse_required=True)
            for r in build.get("move_to_start", [])
        ),
    )


@dataclass
class Dump:
    """A parsed dump file: book metadata and the pieces of every verse entry."""

    book: dict[str, Any]
    entries: dict[Key, list[Piece]]
    ayahs_field_mismatches: int = 0


def load_dump(path: Path, ids: dict[Key, int]) -> Dump:
    """Read ``tafsir-book-<id>.json.gz``; page 0 or a missing page means 'no page'."""
    data = json.loads(gzip.decompress(path.read_bytes()))
    entries: dict[Key, list[Piece]] = {}
    mismatches = 0
    for entry in data["ayahs"]:
        key = (int(entry["surah"]), int(entry["ayah"]))
        if key not in ids:
            raise PipelineError(f"{path.name}: entry for unknown verse {key[0]}:{key[1]}")
        pieces = []
        for item in entry.get("content") or []:
            page = item.get("page")
            page = page if isinstance(page, int) and page > 0 else None
            part = str(item.get("part")).strip() if page is not None else None
            pieces.append(Piece(item.get("text") or "", part, page))
            listed = str(item.get("ayahs", "")).split(",")
            mismatches += str(ids[key]) not in listed
        entries[key] = pieces
    return Dump(data["book"], entries, mismatches)


@dataclass
class Passage:
    """Verses ``first``..``last`` (same surah) and the sections that explain them."""

    first: Key
    last: Key
    sections: list[Section] = field(default_factory=list)


@dataclass
class Assembly:
    """Passages of one book and what happened on the way (for the coverage report)."""

    passages: list[Passage]
    gaps: list[Key]
    gap_merged: list[Key]
    excluded: dict[str, int]  # rule reason -> letters left out
    moved: dict[str, int]  # rule reason -> letters moved to 1:1
    copies: Counter[str]  # e.g. "rep verified", "rel unverified", "unpaged duplicate"
    copy_letters: int
    page_artifacts: int
    ayahs_field_mismatches: int
    accounting: dict[str, int]


def _cut(piece: Piece, rule: PageRule) -> tuple[Piece, str]:
    """Split a piece before the line containing ``rule.from_text``."""
    at = piece.html.index(rule.from_text)
    br = max(piece.html.rfind("<br", 0, at), 0)
    return Piece(piece.html[:br], piece.part, piece.page), piece.html[br:]


def _exclude(entries: dict[Key, list[Piece]], rules: Rules) -> dict[str, int]:
    """Apply ``[[build.exclude]]``; return letters left out per rule (footnotes included)."""
    excluded: dict[str, int] = {}
    for rule in rules.exclude:
        done: dict[Piece, Piece | None] = {}
        for key, pieces in entries.items():
            for piece in pieces:
                if piece in done or not rule.matches(key, piece):
                    continue
                head, tail = _cut(piece, rule) if rule.from_text else (None, piece.html)
                done[piece] = head
                excluded[rule.reason] = excluded.get(rule.reason, 0) + _letters(tail, drop=False)
        if not done:
            raise PipelineError(f"exclude rule matches nothing: {rule}")
        for key, pieces in entries.items():
            replaced = (done.get(p, p) if p in done else p for p in pieces)
            entries[key] = [p for p in replaced if p is not None]
    return excluded


def _move_to_start(entries: dict[Key, list[Piece]], rules: Rules) -> dict[str, int]:
    """Apply ``[[build.move_to_start]]``; return letters moved per rule."""
    moved: dict[str, int] = {}
    start: list[Piece] = []
    for rule in rules.move_to_start:
        found = list(
            dict.fromkeys(
                p for key, ps in sorted(entries.items()) for p in ps if rule.matches(key, p)
            )
        )
        if not found:
            raise PipelineError(f"move_to_start rule matches nothing: {rule}")
        gone = set(found)
        for key, pieces in entries.items():
            entries[key] = [p for p in pieces if p not in gone]
        start += found
        moved[rule.reason] = sum(_letters(p.html, drop=rules.drop_footnotes) for p in found)
    if start:
        entries[(1, 1)] = start + [p for p in entries.get((1, 1), []) if p not in start]
    return moved


def _sections(piece: Piece) -> list[Section]:
    marks = sorted(
        [(m.start(), "rep", int(m.group(1).translate(_DIGITS))) for m in _REP.finditer(piece.html)]
        + [(m.start(), "rel", None) for m in _REL.finditer(piece.html)]
    )
    if not marks:
        return [Section(piece, piece.html, piece.part, piece.page)]
    out = []
    if piece.html[: marks[0][0]].strip():
        out.append(Section(piece, piece.html[: marks[0][0]], piece.part, piece.page))
    for n, (start, label, target) in enumerate(marks):
        stop = marks[n + 1][0] if n + 1 < len(marks) else len(piece.html)
        out.append(Section(piece, piece.html[start:stop], piece.part, piece.page, label, target))
    return out


def _body(section: Section) -> str:
    pattern = _REP if section.label == "rep" else _REL
    return pattern.sub("", section.html, count=1)


class _Ranges:
    """Union of verse ranges within one surah (by ayah number)."""

    def __init__(self) -> None:
        self.spans: list[list[int]] = []

    def add(self, a: int, b: int) -> None:
        merged = [min(a, b), max(a, b)]
        rest = []
        for span in self.spans:
            if span[1] < merged[0] or span[0] > merged[1]:
                rest.append(span)
            else:
                merged = [min(merged[0], span[0]), max(merged[1], span[1])]
        self.spans = sorted([*rest, merged])


class _Assembler:
    """One book's verses, with cached letters and skeletons of every section."""

    def __init__(self, sections: dict[Key, list[Section]], drop: bool) -> None:
        self.sections = sections
        self.drop = drop
        self._letters: dict[Section, int] = {}
        self._skeletons: dict[Section, str] = {}
        self._stored: dict[Key, str] = {}
        self._paged: dict[int, list[tuple[int, str]]] = {}
        self.kept: dict[Key, list[Section]] = {}
        self.ranges: dict[int, _Ranges] = {}
        self.copies: Counter[str] = Counter()

    def letters(self, s: Section) -> int:
        if s not in self._letters:
            self._letters[s] = _letters(s.html, drop=self.drop)
        return self._letters[s]

    def skeleton(self, s: Section) -> str:
        if s not in self._skeletons:
            html = _body(s) if s.label else s.html
            self._skeletons[s] = skeleton(_text(html, self.drop))
        return self._skeletons[s]

    def stored(self, key: Key) -> str:
        """The text stored for a verse so far: its own sections, then the labelled
        sections it kept (verses are processed in order)."""
        if key not in self._stored:
            own = self.sections.get(key, [])
            self._stored[key] = "".join(self.skeleton(s) for s in own if not s.label)
        return self._stored[key]

    def paged(self, surah: int) -> list[tuple[int, str]]:
        if surah not in self._paged:
            self._paged[surah] = [
                (a, "".join(self.skeleton(s) for s in ss if not s.label and s.piece.paged))
                for (su, a), ss in sorted(self.sections.items())
                if su == surah
            ]
        return self._paged[surah]

    def link(self, surah: int, a: int, b: int) -> None:
        self.ranges.setdefault(surah, _Ranges()).add(a, b)

    def find_copy(self, s: Section, key: Key) -> int | None:
        """The ayah whose stored text contains this section's copy, or None."""
        surah, ayah = key
        if not s.label and s.piece.paged:
            return None
        body = self.skeleton(s)
        if len(body) < MIN_COPY_LETTERS:
            return None
        if s.label == "rep":
            target = s.target
            ok = target is not None and body in self.stored((surah, target))
            return target if ok else None
        if s.label == "rel":
            return next(
                (a for a in range(ayah - 1, 0, -1) if body in self.stored((surah, a))), None
            )
        # A repeat of the paged text of this verse, or of a verse with no paged text
        # in between (not, e.g., of an identical refrain further away).
        paged = dict(self.paged(surah))
        for a in sorted(paged, key=lambda b: abs(b - ayah)):
            if any(paged.get(b) for b in range(min(a, ayah) + 1, max(a, ayah))):
                continue
            if body in paged[a]:
                return a
        return None

    def resolve_copies(self) -> set[Section]:
        """Steps 3 and 4: keep or drop every section; link verses joined by a copy."""
        dropped: set[Section] = set()
        for key, ss in sorted(self.sections.items()):
            surah, ayah = key
            keep = []
            for s in ss:
                found = self.find_copy(s, key)
                if found is None:
                    if s.label:
                        self.copies[f"{s.label} unverified"] += 1
                    elif not s.piece.paged and s.html.strip():
                        self.copies["unpaged kept"] += 1
                    keep.append(s)
                    continue
                self.copies[f"{s.label} verified" if s.label else "unpaged duplicate"] += 1
                dropped.add(s)
                if found != ayah:
                    self.link(surah, found, ayah)
            self.kept[key] = keep
            self._stored[key] = self.stored(key) + "".join(
                self.skeleton(s) for s in keep if s.label
            )
            if any(self.letters(s) for s in keep):
                self.link(surah, ayah, ayah)
        return dropped

    def link_shared(self) -> None:
        """Verses holding the same section form one passage, unless verses with text
        of their own lie between them (e.g. a refrain glossed identically)."""
        holders: dict[Section, list[Key]] = {}
        for key, ss in self.kept.items():
            for s in ss:
                holders.setdefault(s, []).append(key)
        has_text = {k for k, ss in self.kept.items() if any(self.letters(s) for s in ss)}
        for keys in holders.values():
            ordered = sorted(keys)
            for (s1, a1), (s2, a2) in itertools.pairwise(ordered):
                if s1 == s2 and not any((s1, a) in has_text for a in range(a1 + 1, a2)):
                    self.link(s1, a1, a2)

    def passages(self) -> list[Passage]:
        out = []
        for surah in sorted(self.ranges):
            for lo, hi in self.ranges[surah].spans:
                passage = Passage((surah, lo), (surah, hi))
                passage.sections = list(
                    dict.fromkeys(
                        s for a in range(lo, hi + 1) for s in self.kept.get((surah, a), [])
                    )
                )
                out.append(passage)
        return out


def assemble(dump: Dump, rules: Rules, verse_text: dict[Key, str]) -> Assembly:
    """Build the passages of one book (see the module docstring)."""
    drop = rules.drop_footnotes
    entries = {k: list(v) for k, v in dump.entries.items()}
    source = sum(_letters(p.html, drop=False) for p in _unique(entries.values()))
    excluded = _exclude(entries, rules)
    moved = _move_to_start(entries, rules)
    work = _Assembler({k: [s for p in ps for s in _sections(p)] for k, ps in entries.items()}, drop)
    work.resolve_copies()
    work.link_shared()
    passages = work.passages()
    gaps, merged = _merge_gaps(passages, verse_text, work)
    stored = {s for p in passages for s in p.sections}
    accounting = _accounting(entries, stored, source, sum(excluded.values()), work)
    artifacts = sum(1 for s in stored if _PAGE_ARTIFACT.match(_text(s.html, drop) or "x"))
    return Assembly(
        passages, gaps, merged, excluded, moved, work.copies, accounting["copies"], artifacts,
        dump.ayahs_field_mismatches, accounting,
    )  # fmt: skip


def _accounting(
    entries: dict[Key, list[Piece]], stored: set[Section], source: int, excluded: int,
    work: _Assembler,
) -> dict[str, int]:  # fmt: skip
    """Every letter of the source is stored once, repeated, a dropped copy, a dropped
    footnote, or excluded edition matter; raise if they do not add up."""
    occurrences = Counter(s for p in _unique(entries.values()) for s in _sections(p))
    out = {"source": source, "excluded": excluded, "footnotes": 0, "copies": 0}
    out |= {"stored": 0, "repeated": 0}
    for sec, count in occurrences.items():
        kept = work.letters(sec)
        out["footnotes"] += count * (_letters(sec.html, drop=False) - kept)
        if sec in stored:
            out["stored"] += kept
            out["repeated"] += (count - 1) * kept
        else:
            out["copies"] += count * kept
    if sum(v for k, v in out.items() if k != "source") != source:
        raise PipelineError(f"letters do not add up: {out}")
    return out


def _unique(groups: Any) -> list[Any]:
    return list(dict.fromkeys(x for group in groups for x in group))


def _letters(html: str, *, drop: bool) -> int:
    return len(source_letters(html, drop_footnotes=drop))


def _text(html: str, drop: bool) -> str:
    return source_letters(html, drop_footnotes=drop)


def _merge_gaps(
    passages: list[Passage], verse_text: dict[Key, str], work: _Assembler
) -> tuple[list[Key], list[Key]]:
    """Extend passages over following verses they quote (K4); return gaps and merges."""
    covered = {(p.first[0], a) for p in passages for a in range(p.first[1], p.last[1] + 1)}
    by_end = {p.last: p for p in passages}
    gaps, merged = [], []
    texts: dict[int, str] = {}
    for key in sorted(verse_text):
        if key in covered:
            continue
        surah, ayah = key
        before = by_end.get((surah, ayah - 1))
        probe = skeleton(" ".join(normalize(verse_text[key]).split()[:GAP_WORDS]))
        if before is not None and len(probe) >= MIN_GAP_PROBE:
            if id(before) not in texts:
                texts[id(before)] = "".join(work.skeleton(s) for s in before.sections)
            if probe in texts[id(before)]:
                del by_end[before.last]
                before.last = key
                by_end[key] = before
                merged.append(key)
                continue
        gaps.append(key)
    return gaps, merged
