"""Alignment of QAC words with the Tanzil Uthmani text (spec §5.3.1).

Rules (docs/qac-alignment.md):

A1  Tanzil writes pause marks, the sajdah sign and the rub-el-hizb sign as
    separate tokens. A token made only of these marks is not a word; it is
    attached to the preceding word, so that ``" ".join(words.text_ar)`` is
    exactly ``verses.text_uthmani``.
A2  For every verse, the Tanzil words pair one to one with the QAC words.
M   Where QAC writes one word that Tanzil writes as two tokens (QAC follows
    Tanzil 1.0.2; 1.1 splits e.g. بعدما), the two tokens form one word if their
    concatenation (with or without the space) matches the QAC word. Applied
    only in verses whose word counts differ.
A3  For every word, the concatenated QAC segments (converted to Arabic) are
    compared with the Tanzil word at increasing levels of tolerance:
      exact      identical code points;
      canonical  identical after removing tatweel and putting combining marks
                 in canonical (NFD) order;
      edition    identical after also applying the documented spelling
                 differences between Tanzil 1.0.2 (QAC's base) and 1.1:
                   E1 hamza above on a tatweel (1.1) = standalone hamza (1.0.2),
                   E2 small high yeh U+06E7 = small yeh U+06E6,
                   E3 alif maksura + dagger alif = tatweel + dagger alif;
      skeleton   identical after the search normalization (docs/normalization.md);
      mismatch   anything else.
    The gate accepts exact, canonical and edition (approved in the M1b review).

The comparison never changes stored text: words.text_ar is Tanzil's text and
word_segments.text_ar is QAC's form, each verbatim.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from pipeline.buckwalter import form_to_arabic
from pipeline.errors import PipelineError
from pipeline.normalize import normalize
from pipeline.qac import Segment

#: Characters that make up a standalone mark token (A1): pause marks
#: U+06D6–06DC, rub el hizb U+06DE, place of sajdah U+06E9.
MARK_TOKEN_CHARS = frozenset([chr(c) for c in range(0x06D6, 0x06DC + 1)] + ["\u06de", "\u06e9"])
LEVELS = ("exact", "canonical", "edition", "skeleton", "mismatch")
#: Levels the alignment gate accepts (approved after reviewing the report).
ACCEPTED_LEVELS = frozenset({"exact", "canonical", "edition"})
TATWEEL = "\u0640"
_MARKS = "\u064b-\u065f\u0670\u06d6-\u06ed"
#: E1: tatweel carrying hamza above (and any vowel marks) = standalone hamza.
_HAMZA_ON_TATWEEL = re.compile(f"{TATWEEL}([{_MARKS}]*?)\u0654")


@dataclass(frozen=True)
class TanzilWord:
    """One word of a verse: the bare token and the stored text (token + trailing marks)."""

    position: int
    token: str
    text_ar: str


@dataclass(frozen=True)
class AlignedWord:
    """A Tanzil word paired with its QAC segments; ``position`` is QAC's word number."""

    position: int
    text_ar: str
    segments: list[Segment]


@dataclass(frozen=True)
class WordAlignment:
    """The comparison of one Tanzil word with its QAC segments."""

    surah: int
    ayah: int
    position: int
    tanzil: str
    qac: str
    level: str
    merged: bool = False


@dataclass
class AlignmentReport:
    """Per-word results, unresolved verse-level count mismatches and the pairings."""

    words: list[WordAlignment] = field(default_factory=list)
    count_mismatches: list[tuple[int, int, int, int]] = field(default_factory=list)
    aligned: dict[tuple[int, int], list[AlignedWord]] = field(default_factory=dict)

    def levels(self) -> Counter[str]:
        return Counter(w.level for w in self.words)

    def merged(self) -> list[WordAlignment]:
        return [w for w in self.words if w.merged]

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


def _edition(text: str) -> str:
    text = _HAMZA_ON_TATWEEL.sub("\u0621\\1", text)  # E1
    text = text.replace("\u06e7", "\u06e6")  # E2
    text = text.replace("\u0649\u0670", TATWEEL + "\u0670")  # E3
    return _canonical(text)


def compare(tanzil: str, qac: str) -> str:
    """Return the first level (A3) at which the two spellings agree."""
    if tanzil == qac:
        return "exact"
    if _canonical(tanzil) == _canonical(qac):
        return "canonical"
    if _edition(tanzil) == _edition(qac):
        return "edition"
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


def _pair_verse(
    key: tuple[int, int],
    words: list[TanzilWord],
    qac_words: list[list[Segment]],
    report: AlignmentReport,
) -> None:
    surah, ayah = key
    may_merge = len(words) != len(qac_words)
    aligned: list[AlignedWord] = []
    results: list[WordAlignment] = []
    i = 0
    for number, segments in enumerate(qac_words, start=1):
        joined = "".join(form_to_arabic(seg.form) for seg in segments)
        if i >= len(words):
            break
        level = compare(words[i].token, joined)
        if level not in ACCEPTED_LEVELS and may_merge and i + 1 < len(words):
            for sep in ("", " "):
                merged_token = words[i].token + sep + words[i + 1].token
                merged_level = compare(merged_token, joined)
                if merged_level in ACCEPTED_LEVELS:
                    text_ar = words[i].text_ar + " " + words[i + 1].text_ar
                    results.append(
                        WordAlignment(surah, ayah, number, merged_token, joined, merged_level, True)
                    )
                    aligned.append(AlignedWord(number, text_ar, segments))
                    i += 2
                    break
            else:
                results.append(WordAlignment(surah, ayah, number, words[i].token, joined, level))
                aligned.append(AlignedWord(number, words[i].text_ar, segments))
                i += 1
            continue
        results.append(WordAlignment(surah, ayah, number, words[i].token, joined, level))
        aligned.append(AlignedWord(number, words[i].text_ar, segments))
        i += 1
    if i != len(words) or len(aligned) != len(qac_words):
        report.count_mismatches.append((surah, ayah, len(words), len(qac_words)))
        return
    report.words.extend(results)
    report.aligned[key] = aligned


def align(
    verses: dict[tuple[int, int], str], qac: dict[tuple[int, int], list[list[Segment]]]
) -> AlignmentReport:
    """Align every verse of ``verses`` (Tanzil Uthmani text by (surah, ayah)) with QAC."""
    if set(verses) != set(qac):
        missing = sorted(set(verses) - set(qac))[:5]
        extra = sorted(set(qac) - set(verses))[:5]
        raise PipelineError(f"QAC verses differ from Tanzil: missing {missing}, extra {extra}")
    report = AlignmentReport()
    for key, text in sorted(verses.items()):
        _pair_verse(key, tanzil_words(text, f"{key[0]}:{key[1]}"), qac[key], report)
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
    merged = report.merged()
    lines += ["", f"## Tokens merged by rule M ({len(merged)})", ""]
    lines += [
        f"- {w.surah}:{w.ayah}:{w.position}: Tanzil {w.tanzil} = QAC {w.qac} ({w.level})"
        for w in merged
    ] or ["None."]
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
