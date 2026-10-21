"""Alignment of QAC words with the Tanzil Uthmani text (spec §5.3.1).

Rules (docs/qac-alignment.md):

A1  Tanzil writes pause marks, the sajdah sign and the rub-el-hizb sign as
    separate tokens. A token made only of these marks is not a word; it is
    attached to the preceding word, so that ``" ".join(words.text_ar)`` is
    exactly ``verses.text_uthmani``.
A2  For every verse, the number of Tanzil words equals the number of QAC words.
A3  For every word, the concatenated QAC segments (converted to Arabic) are
    compared with the Tanzil word at increasing levels of tolerance:
      exact      identical code points;
      canonical  identical after removing tatweel and putting combining marks
                 in canonical (NFD) order;
      skeleton   identical after the search normalization (docs/normalization.md),
                 i.e. same letters, marks ignored;
      mismatch   anything else.
    Which levels the gate accepts is decided from the report (ACCEPTED_LEVELS).

The comparison never changes stored text: words.text_ar is Tanzil's text and
word_segments.text_ar is QAC's form, each verbatim.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from pipeline.buckwalter import to_arabic
from pipeline.errors import PipelineError
from pipeline.normalize import normalize
from pipeline.qac import Segment

#: Characters that make up a standalone mark token (A1): pause marks
#: U+06D6–06DC, rub el hizb U+06DE, place of sajdah U+06E9.
MARK_TOKEN_CHARS = frozenset([chr(c) for c in range(0x06D6, 0x06DC + 1)] + ["\u06de", "\u06e9"])
LEVELS = ("exact", "canonical", "skeleton", "mismatch")
#: Levels the alignment gate accepts. Set after reviewing the alignment report.
ACCEPTED_LEVELS = frozenset({"exact", "canonical"})
TATWEEL = "\u0640"


@dataclass(frozen=True)
class TanzilWord:
    """One word of a verse: the bare token and the stored text (token + trailing marks)."""

    position: int
    token: str
    text_ar: str


@dataclass(frozen=True)
class WordAlignment:
    """The comparison of one Tanzil word with its QAC segments."""

    surah: int
    ayah: int
    position: int
    tanzil: str
    qac: str
    level: str


@dataclass
class AlignmentReport:
    """Per-word results plus verse-level word-count mismatches."""

    words: list[WordAlignment] = field(default_factory=list)
    count_mismatches: list[tuple[int, int, int, int]] = field(default_factory=list)

    def levels(self) -> Counter[str]:
        return Counter(w.level for w in self.words)

    def failures(self) -> list[str]:
        """Messages for everything the gate does not accept."""
        out = [
            f"{s}:{a}: Tanzil has {t} words, QAC has {q}" for s, a, t, q in self.count_mismatches
        ]
        out += [
            f"{w.surah}:{w.ayah}:{w.position}: {w.level}: Tanzil {w.tanzil!r} vs QAC {w.qac!r}"
            for w in self.words
            if w.level not in ACCEPTED_LEVELS
        ]
        return out


def is_mark_token(token: str) -> bool:
    """True for a token made only of pause/sajdah/hizb marks (rule A1)."""
    return bool(token) and all(ch in MARK_TOKEN_CHARS for ch in token)


def tanzil_words(text: str, where: str) -> list[TanzilWord]:
    """Split a Tanzil Uthmani verse into words, attaching mark tokens to the previous word."""
    words: list[list[str]] = []
    for token in text.split(" "):
        if not token:
            raise PipelineError(f"{where}: empty token (double space) in Tanzil text")
        if is_mark_token(token):
            if not words:
                raise PipelineError(f"{where}: verse starts with a mark token {token!r}")
            words[-1].append(token)
        else:
            words.append([token])
    result = [TanzilWord(i, group[0], " ".join(group)) for i, group in enumerate(words, start=1)]
    if " ".join(w.text_ar for w in result) != text:
        raise PipelineError(f"{where}: words do not join back to the verse text")
    return result


def _canonical(text: str) -> str:
    return unicodedata.normalize("NFD", text.replace(TATWEEL, ""))


def compare(tanzil: str, qac: str) -> str:
    """Return the first level (A3) at which the two spellings agree."""
    if tanzil == qac:
        return "exact"
    if _canonical(tanzil) == _canonical(qac):
        return "canonical"
    if normalize(tanzil) == normalize(qac):
        return "skeleton"
    return "mismatch"


def group_words(segments: list[Segment]) -> dict[tuple[int, int], list[list[Segment]]]:
    """Group QAC segments into verses and words, checking that numbering is contiguous."""
    verses: dict[tuple[int, int], list[list[Segment]]] = {}
    for seg in segments:
        words = verses.setdefault((seg.surah, seg.ayah), [])
        if seg.word == len(words) + 1 and seg.segment == 1:
            words.append([seg])
        elif seg.word == len(words) and seg.segment == words[-1][-1].segment + 1:
            words[-1].append(seg)
        else:
            raise PipelineError(f"QAC line {seg.line}: location {seg.location} is out of order")
    return verses


def align(
    verses: dict[tuple[int, int], str], qac: dict[tuple[int, int], list[list[Segment]]]
) -> AlignmentReport:
    """Align every verse of ``verses`` (Tanzil Uthmani text by (surah, ayah)) with QAC."""
    if set(verses) != set(qac):
        missing = sorted(set(verses) - set(qac))[:5]
        extra = sorted(set(qac) - set(verses))[:5]
        raise PipelineError(f"QAC verses differ from Tanzil: missing {missing}, extra {extra}")
    report = AlignmentReport()
    for (surah, ayah), text in sorted(verses.items()):
        words = tanzil_words(text, f"{surah}:{ayah}")
        qac_words = qac[(surah, ayah)]
        if len(words) != len(qac_words):
            report.count_mismatches.append((surah, ayah, len(words), len(qac_words)))
            continue
        for word, segments in zip(words, qac_words, strict=True):
            joined = "".join(to_arabic(seg.form) for seg in segments)
            report.words.append(
                WordAlignment(
                    surah, ayah, word.position, word.token, joined, compare(word.token, joined)
                )
            )
    return report


def render_report(report: AlignmentReport, *, limit: int = 200) -> str:
    """A Markdown report: counts per level, count mismatches, and every non-exact word."""
    levels = report.levels()
    lines = [
        "# QAC ↔ Tanzil alignment report",
        "",
        f"Words compared: {len(report.words):,}",
        "",
        "| Level | Words | Accepted by the gate |",
        "|---|---|---|",
        *[
            f"| {level} | {levels[level]:,} | {'yes' if level in ACCEPTED_LEVELS else 'no'} |"
            for level in LEVELS
        ],
        "",
        f"## Verses with different word counts ({len(report.count_mismatches)})",
        "",
    ]
    lines += [f"- {s}:{a}: Tanzil {t}, QAC {q}" for s, a, t, q in report.count_mismatches] or [
        "None."
    ]
    for level in LEVELS[1:]:
        rows = [w for w in report.words if w.level == level]
        lines += ["", f"## {level} ({len(rows):,})", ""]
        if not rows:
            lines.append("None.")
            continue
        lines += [
            "| Location | Tanzil | QAC | Tanzil code points | QAC code points |",
            "|---|---|---|---|---|",
        ]
        for w in rows[:limit]:
            lines.append(
                f"| {w.surah}:{w.ayah}:{w.position} | {w.tanzil} | {w.qac} | "
                f"{_points(w.tanzil)} | {_points(w.qac)} |"
            )
        if len(rows) > limit:
            lines.append(f"\n… {len(rows) - limit:,} more (see the JSON report).")
    return "\n".join(lines) + "\n"


def _points(text: str) -> str:
    return " ".join(f"{ord(ch):04X}" for ch in text)
