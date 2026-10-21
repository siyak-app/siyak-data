"""Parser for the Quranic Arabic Corpus morphology file (v0.4).

The file has a ``#`` comment header (the copyright notice that must ship with
the data), a column header ``LOCATION FORM TAG FEATURES`` and one
tab-separated row per segment::

    (1:1:1:1)\tbi\tP\tPREFIX|bi+
    (1:1:1:2)\tsomi\tN\tSTEM|POS:N|LEM:{som|ROOT:smw|M|GEN

Parsing keeps every value exactly as written. :func:`interpret` maps the
feature tokens to stable English keys (docs/pack-format.md §7); a token it
does not know is an error, so no tag is ever dropped silently.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.errors import PipelineError

COLUMNS = "LOCATION\tFORM\tTAG\tFEATURES"
_LOCATION = re.compile(r"^\((\d+):(\d+):(\d+):(\d+)\)$")
_PGN = re.compile(r"^([123])?([MF])?([SDP])?$")
_VERB_FORM = re.compile(r"^\((I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\)$")
KINDS = {"PREFIX": "prefix", "STEM": "stem", "SUFFIX": "suffix"}

#: Single-token features: token -> (key, value).
SIMPLE: dict[str, tuple[str, str]] = {
    "PERF": ("aspect", "PERF"),
    "IMPF": ("aspect", "IMPF"),
    "IMPV": ("aspect", "IMPV"),
    "MOOD:IND": ("mood", "IND"),
    "MOOD:SUBJ": ("mood", "SUBJ"),
    "MOOD:JUS": ("mood", "JUS"),
    "VN": ("derivation", "VN"),
    "DEF": ("state", "DEF"),
    "INDEF": ("state", "INDEF"),
    "NOM": ("case", "NOM"),
    "ACC": ("case", "ACC"),
    "GEN": ("case", "GEN"),
}

#: Stable feature keys, in display order (docs/pack-format.md §7).
FEATURE_KEYS = (
    "prefix", "suffix", "person", "gender", "number", "aspect", "mood", "voice",
    "verb_form", "derivation", "state", "case", "special",
)  # fmt: skip


@dataclass(frozen=True)
class Segment:
    """One row of the QAC file, verbatim."""

    surah: int
    ayah: int
    word: int
    segment: int
    form: str
    tag: str
    features: tuple[str, ...]
    line: int

    @property
    def location(self) -> str:
        return f"{self.surah}:{self.ayah}:{self.word}:{self.segment}"


@dataclass(frozen=True)
class QacFile:
    """The parsed file: its comment header and all segment rows in file order."""

    notice: str
    segments: list[Segment]


@dataclass
class Interpreted:
    """A segment's features split into the columns of ``word_segments``."""

    kind: str
    pos: str
    lemma: str | None = None
    root: str | None = None
    features: dict[str, str] = field(default_factory=dict)


def parse_qac(path: Path) -> QacFile:
    """Parse the QAC morphology file; fail on any malformed line."""
    header: list[str] = []
    segments: list[Segment] = []
    seen_columns = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("#"):
            header.append(line)
            continue
        if not line.strip():
            continue
        if line == COLUMNS:
            seen_columns = True
            continue
        if not seen_columns:
            raise PipelineError(f"{path}:{number}: data before the column header {COLUMNS!r}")
        parts = line.split("\t")
        location = _LOCATION.match(parts[0]) if len(parts) == 4 else None
        if location is None:
            raise PipelineError(f"{path}:{number}: not a 'LOCATION FORM TAG FEATURES' row")
        s, a, w, k = (int(g) for g in location.groups())
        segments.append(Segment(s, a, w, k, parts[1], parts[2], tuple(parts[3].split("|")), number))
    if not segments:
        raise PipelineError(f"{path}: no segment rows found")
    return QacFile(notice="\n".join(header), segments=segments)


def _set(out: Interpreted, key: str, value: str, seg: Segment) -> None:
    if key in out.features:
        raise PipelineError(f"QAC {seg.location}: feature '{key}' given twice in {seg.features}")
    out.features[key] = value


def interpret(seg: Segment) -> Interpreted:
    """Map a segment's feature tokens to kind, POS, lemma, root and feature keys."""
    tokens = list(seg.features)
    if not tokens or tokens[0] not in KINDS:
        raise PipelineError(f"QAC {seg.location}: first feature must be PREFIX, STEM or SUFFIX")
    out = Interpreted(kind=KINDS[tokens[0]], pos=seg.tag)
    unknown: list[str] = []
    i = 1
    while i < len(tokens):
        following = tokens[i + 1] if i + 1 < len(tokens) else ""
        consumed = _keyed(out, tokens[i], seg) or _plain(out, tokens[i], following, seg)
        if consumed == 0:
            unknown.append(tokens[i])
            consumed = 1
        i += consumed
    if unknown:
        raise PipelineError(f"QAC {seg.location}: unknown feature token(s) {unknown}")
    return out


def _keyed(out: Interpreted, token: str, seg: Segment) -> int:
    """Tokens of the form KEY:value and affixes; return 1 if handled, else 0."""
    if token.startswith("POS:"):
        if token[4:] != seg.tag:
            raise PipelineError(f"QAC {seg.location}: {token} differs from tag {seg.tag}")
    elif token.startswith("LEM:"):
        out.lemma = token[4:]
    elif token.startswith("ROOT:"):
        out.root = token[5:]
    elif token.startswith("SP:"):
        _set(out, "special", token[3:], seg)
    elif token.startswith("PRON:") and token[5:] and _PGN.match(token[5:]):
        _set_pgn(out, token[5:], seg)
    elif token.endswith("+") and len(token) > 1:
        _set(out, "prefix", token, seg)
    elif token.startswith("+") and len(token) > 1:
        _set(out, "suffix", token, seg)
    else:
        return 0
    return 1


def _plain(out: Interpreted, token: str, following: str, seg: Segment) -> int:
    """Bare feature codes; return the number of tokens consumed (0 if unknown)."""
    if token in ("ACT", "PASS") and following == "PCPL":
        _set(out, "derivation", f"{token} PCPL", seg)
        return 2
    if token in ("ACT", "PASS"):
        _set(out, "voice", token, seg)
    elif token in SIMPLE:
        _set(out, *SIMPLE[token], seg)
    elif (form := _VERB_FORM.match(token)) is not None:
        _set(out, "verb_form", form.group(1), seg)
    elif token and _PGN.match(token):
        _set_pgn(out, token, seg)
    else:
        return 0
    return 1


def _set_pgn(out: Interpreted, code: str, seg: Segment) -> None:
    match = _PGN.match(code)
    assert match is not None
    for key, value in zip(("person", "gender", "number"), match.groups(), strict=True):
        if value:
            _set(out, key, value, seg)


def unknown_tokens(segments: Iterable[Segment]) -> Counter[str]:
    """Count feature tokens :func:`interpret` rejects (for reports while extending it)."""
    counts: Counter[str] = Counter()
    for seg in segments:
        try:
            interpret(seg)
        except PipelineError as exc:
            counts[str(exc).split(": ", 1)[1]] += 1
    return counts
