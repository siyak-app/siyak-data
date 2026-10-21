"""Arabic search normalization: the contract shared with the app's Rust code.

The app normalizes every search query with these rules, and the pipeline fills
``verses_fts`` with ``normalize(text_clean)``, so query and index meet in the
same form. The Rust implementation must give identical output;
``tests/normalize_vectors.json`` is the shared test set. Rules and their ids are
documented in docs/normalization.md.

Rules work on explicit code points only: no global Unicode normalization form
is applied, so Python and Rust cannot drift apart through different Unicode
database versions. The one exception is N10, which applies NFKC to Arabic
presentation forms only; their decompositions have been stable for decades.

Order: N10 → (N11, N1–N4 removals and N5–N9 letter mappings in one pass) → N12.
Removals and mappings do not interact (no mapping produces a removed character
and no removal produces a mapped letter), so a single translation table is
equivalent to applying them one by one. The result is idempotent.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Iterable


def _span(first: int, last: int) -> range:
    return range(first, last + 1)


#: N10: Arabic Presentation Forms-A and -B, decomposed with NFKC.
PRESENTATION_FORMS: tuple[range, ...] = (_span(0xFB50, 0xFDFF), _span(0xFE70, 0xFEFF))

#: Characters removed, by rule id.
REMOVALS: dict[str, tuple[range, ...]] = {
    # Invisible format characters: zero-width space/joiners, bidi marks and
    # embeddings/isolates, Arabic letter mark, zero-width no-break space (BOM).
    "N11": (
        _span(0x200B, 0x200F),
        _span(0x202A, 0x202E),
        _span(0x2066, 0x2069),
        _span(0x061C, 0x061C),
        _span(0xFEFF, 0xFEFF),
    ),
    # Harakat: tanween, fatha, damma, kasra, shadda, sukun, maddah, combining
    # hamza above/below, subscript alef and the other combining marks U+0656–065F.
    "N1": (_span(0x064B, 0x065F),),
    # Superscript (dagger) alef.
    "N2": (_span(0x0670, 0x0670),),
    # Quranic annotation marks: honorifics and small high marks (U+0610–061A),
    # small high ligatures, pause marks, end of ayah, rub el hizb, sajdah, small
    # waw/yeh and other Quranic marks (U+06D6–06ED), extended Quranic marks
    # (U+08D3–08FF).
    "N3": (_span(0x0610, 0x061A), _span(0x06D6, 0x06ED), _span(0x08D3, 0x08FF)),
    # Tatweel (kashida).
    "N4": (_span(0x0640, 0x0640),),
}

#: Letter mappings, by rule id.
MAPPINGS: dict[str, dict[str, str]] = {
    # Alef variants: hamza above, hamza below, madda, wasla.
    "N5": {"\u0623": "\u0627", "\u0625": "\u0627", "\u0622": "\u0627", "\u0671": "\u0627"},
    # Alef maqsura → yeh.
    "N6": {"\u0649": "\u064a"},
    # Teh marbuta → heh.
    "N7": {"\u0629": "\u0647"},
    # Hamza on waw → waw, hamza on yeh → yeh.
    "N8": {"\u0624": "\u0648", "\u0626": "\u064a"},
    # Persian/Urdu letters: keheh → kaf; Farsi yeh, yeh barree → yeh;
    # heh goal, heh doachashmee, heh with yeh above → heh.
    "N9": {
        "\u06a9": "\u0643",
        "\u06cc": "\u064a",
        "\u06d2": "\u064a",
        "\u06c1": "\u0647",
        "\u06be": "\u0647",
        "\u06c0": "\u0647",
    },
}

#: N12: the Unicode White_Space property (identical to Rust's char::is_whitespace).
WHITESPACE: frozenset[str] = frozenset(
    chr(c)
    for c in (
        *_span(0x0009, 0x000D),
        0x0020,
        0x0085,
        0x00A0,
        0x1680,
        *_span(0x2000, 0x200A),
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
    )
)

#: Every rule id, in application order.
RULE_IDS: tuple[str, ...] = (
    "N10",
    "N11",
    "N1",
    "N2",
    "N3",
    "N4",
    "N5",
    "N6",
    "N7",
    "N8",
    "N9",
    "N12",
)


def _build_table() -> dict[int, str | None]:
    table: dict[int, str | None] = {}
    for spans in REMOVALS.values():
        for span in spans:
            for code in span:
                table[code] = None
    for mapping in MAPPINGS.values():
        for src, dst in mapping.items():
            table[ord(src)] = dst
    return table


_TABLE = _build_table()
_RULE_OF: dict[str, str] = {
    **{chr(code): rule for rule, spans in REMOVALS.items() for span in spans for code in span},
    **{src: rule for rule, mapping in MAPPINGS.items() for src in mapping},
}


def _is_presentation_form(ch: str) -> bool:
    code = ord(ch)
    return any(code in span for span in PRESENTATION_FORMS)


def _decompose_presentation_forms(text: str) -> str:
    return "".join(
        unicodedata.normalize("NFKC", ch) if _is_presentation_form(ch) else ch for ch in text
    )


def _collapse_whitespace(text: str) -> str:
    out: list[str] = []
    pending_space = False
    for ch in text:
        if ch in WHITESPACE:
            pending_space = bool(out)
            continue
        if pending_space:
            out.append(" ")
            pending_space = False
        out.append(ch)
    return "".join(out)


def normalize(text: str) -> str:
    """Normalize Arabic text for search (rules N1–N12, docs/normalization.md)."""
    text = _decompose_presentation_forms(text)
    text = text.translate(_TABLE)
    return _collapse_whitespace(text)


def rule_counts(texts: Iterable[str]) -> Counter[str]:
    """Count how many characters each rule changes in ``texts`` (for build reports).

    Character rules count changed characters; N12 counts texts whose whitespace
    was changed.
    """
    counts: Counter[str] = Counter()
    for raw in texts:
        presentation = sum(
            1 for ch in raw if _is_presentation_form(ch) and unicodedata.normalize("NFKC", ch) != ch
        )
        if presentation:
            counts["N10"] += presentation
        text = _decompose_presentation_forms(raw)
        for ch in text:
            rule = _RULE_OF.get(ch)
            if rule is not None:
                counts[rule] += 1
        translated = text.translate(_TABLE)
        if _collapse_whitespace(translated) != translated:
            counts["N12"] += 1
    return counts
