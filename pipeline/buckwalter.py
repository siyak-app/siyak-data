"""Buckwalter transliteration used by the Quranic Arabic Corpus, to Arabic script.

The table is QAC's extended Buckwalter scheme, copied from
https://corpus.quran.com/java/buckwalter.jsp (retrieved 2026-10-21): the 36
letters of standard Buckwalter, the diacritics, and QAC's extensions for
Quranic marks. Every character of the QAC file must be in this table;
an unknown character is an error, never skipped (tests/test_buckwalter.py
checks the whole file when it is in .cache/).
"""

from __future__ import annotations

from pipeline.errors import PipelineError

#: Buckwalter character → Unicode code point, in the order of QAC's table.
TABLE: dict[str, str] = {
    "'": "\u0621",  # hamza
    ">": "\u0623",  # alif + hamza above
    "&": "\u0624",  # waw + hamza above
    "<": "\u0625",  # alif + hamza below
    "}": "\u0626",  # ya + hamza above
    "A": "\u0627",  # alif
    "b": "\u0628",  # ba
    "p": "\u0629",  # ta marbuta
    "t": "\u062a",  # ta
    "v": "\u062b",  # tha
    "j": "\u062c",  # jeem
    "H": "\u062d",  # hha
    "x": "\u062e",  # kha
    "d": "\u062f",  # dal
    "*": "\u0630",  # thal
    "r": "\u0631",  # ra
    "z": "\u0632",  # zain
    "s": "\u0633",  # seen
    "$": "\u0634",  # sheen
    "S": "\u0635",  # sad
    "D": "\u0636",  # dad
    "T": "\u0637",  # ta (emphatic)
    "Z": "\u0638",  # dha
    "E": "\u0639",  # ain
    "g": "\u063a",  # ghain
    "_": "\u0640",  # tatweel
    "f": "\u0641",  # fa
    "q": "\u0642",  # qaf
    "k": "\u0643",  # kaf
    "l": "\u0644",  # lam
    "m": "\u0645",  # meem
    "n": "\u0646",  # noon
    "h": "\u0647",  # ha
    "w": "\u0648",  # waw
    "Y": "\u0649",  # alif maksura
    "y": "\u064a",  # ya
    "F": "\u064b",  # fathatan
    "N": "\u064c",  # dammatan
    "K": "\u064d",  # kasratan
    "a": "\u064e",  # fatha
    "u": "\u064f",  # damma
    "i": "\u0650",  # kasra
    "~": "\u0651",  # shadda
    "o": "\u0652",  # sukun
    "^": "\u0653",  # maddah
    "#": "\u0654",  # hamza above
    "`": "\u0670",  # alif khanjareeya (superscript alef)
    "{": "\u0671",  # alif + hamzat wasl
    ":": "\u06dc",  # small high seen
    "@": "\u06df",  # small high rounded zero
    '"': "\u06e0",  # small high upright rectangular zero
    "[": "\u06e2",  # small high meem (isolated form)
    ";": "\u06e3",  # small low seen
    ",": "\u06e5",  # small waw
    ".": "\u06e6",  # small ya
    "!": "\u06e8",  # small high noon
    "-": "\u06ea",  # empty centre low stop
    "+": "\u06eb",  # empty centre high stop
    "%": "\u06ec",  # rounded high stop with filled centre
    "]": "\u06ed",  # small low meem
}

REVERSE: dict[str, str] = {arabic: latin for latin, arabic in TABLE.items()}


def to_arabic(text: str) -> str:
    """Convert QAC Buckwalter to Arabic script; raise on any unknown character."""
    try:
        return "".join(TABLE[ch] for ch in text)
    except KeyError as exc:
        raise PipelineError(
            f"unknown Buckwalter character {exc.args[0]!r} (U+{ord(exc.args[0]):04X}) in {text!r}"
        ) from None


def to_buckwalter(text: str) -> str:
    """Convert Arabic script to QAC Buckwalter (used to write test fixtures)."""
    try:
        return "".join(REVERSE[ch] for ch in text)
    except KeyError as exc:
        raise PipelineError(
            f"no Buckwalter character for U+{ord(exc.args[0]):04X} in {text!r}"
        ) from None


def root_to_arabic(root: str) -> str:
    """Convert a QAC root (e.g. ``qwl``) to spaced Arabic letters (``ق و ل``)."""
    return " ".join(to_arabic(letter) for letter in root)
