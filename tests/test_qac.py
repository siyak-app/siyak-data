"""Parser tests on small synthetic rows in the QAC v0.4 format (not QAC data)."""

from pathlib import Path

import pytest

from pipeline.errors import PipelineError
from pipeline.qac import COLUMNS, Segment, interpret, parse_qac


def seg(tag: str, features: str) -> Segment:
    return Segment(9, 9, 9, 1, "x", tag, tuple(features.split("|")), 1)


def test_notice_keeps_crlf(tmp_path: Path) -> None:
    path = tmp_path / "q.txt"
    path.write_bytes(f"# a\r\n#\r\n\r\n{COLUMNS}\r\n(1:1:1:1)\tbi\tP\tPREFIX|bi+\r\n".encode())
    parsed = parse_qac(path)
    assert parsed.notice == "# a\r\n#\r\n\r\n"
    assert parsed.segments[0].features == ("PREFIX", "bi+")


def test_parse_keeps_rows_verbatim(tmp_path: Path) -> None:
    path = tmp_path / "q.txt"
    path.write_text(
        f"# notice line 1\n#  line 2\n\n{COLUMNS}\n"
        "(1:2:3:1)\twa\tCONJ\tPREFIX|w:CONJ+\n"
        "(1:2:3:2)\tkataba\tV\tSTEM|POS:V|PERF|LEM:kataba|ROOT:ktb|3MS\n",
        encoding="utf-8",
    )
    parsed = parse_qac(path)
    assert parsed.notice == "# notice line 1\n#  line 2\n\n"
    assert [s.location for s in parsed.segments] == ["1:2:3:1", "1:2:3:2"]
    assert parsed.segments[1].form == "kataba"
    assert parsed.segments[1].features[-1] == "3MS"


@pytest.mark.parametrize(
    "body",
    [
        "(1:1:1:1)\tbi\tP\tPREFIX|bi+\n",  # no column header
        f"{COLUMNS}\n1:1:1:1\tbi\tP\tPREFIX|bi+\n",  # location without parentheses
        f"{COLUMNS}\n(1:1:1:1)\tbi\tP\n",  # missing column
    ],
)
def test_malformed_files_fail(tmp_path: Path, body: str) -> None:
    path = tmp_path / "q.txt"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(PipelineError):
        parse_qac(path)


def test_interpret_verb_stem() -> None:
    out = interpret(seg("V", "STEM|POS:V|IMPF|(IV)|LEM:>akorama|ROOT:krm|3MP|PASS|MOOD:SUBJ"))
    assert (out.kind, out.pos, out.lemma, out.root) == ("stem", "V", ">akorama", "krm")
    assert out.features == {
        "aspect": "IMPF",
        "verb_form": "IV",
        "person": "3",
        "gender": "M",
        "number": "P",
        "voice": "PASS",
        "mood": "SUBJ",
    }


def test_interpret_participle_noun() -> None:
    out = interpret(seg("N", "STEM|POS:N|ACT|PCPL|(VIII)|LEM:x|ROOT:Hdy|MP|INDEF|GEN"))
    assert out.features == {
        "derivation": "ACT PCPL",
        "verb_form": "VIII",
        "gender": "M",
        "number": "P",
        "state": "INDEF",
        "case": "GEN",
    }


@pytest.mark.parametrize(
    ("tag", "features", "expected"),
    [
        ("DET", "PREFIX|Al+", {"prefix": "Al+"}),
        ("CONJ", "PREFIX|w:CONJ+", {"prefix": "w:CONJ+"}),
        ("PRON", "SUFFIX|PRON:3FS", {"person": "3", "gender": "F", "number": "S"}),
        ("VOC", "SUFFIX|+VOC", {"suffix": "+VOC"}),
        ("V", "STEM|POS:V|PERF|LEM:kaAna|ROOT:kwn|SP:kaAn|3MS",
         {"aspect": "PERF", "special": "kaAn", "person": "3", "gender": "M", "number": "S"}),
    ],
)  # fmt: skip
def test_interpret_affixes(tag: str, features: str, expected: dict[str, str]) -> None:
    assert interpret(seg(tag, features)).features == expected


@pytest.mark.parametrize(
    ("tag", "features", "message"),
    [
        ("N", "POS:N|GEN", "first feature must be"),
        ("N", "STEM|POS:V", "differs from tag N"),
        ("N", "STEM|POS:N|GEN|ACC", "feature 'case' given twice"),
        ("N", "STEM|POS:N|WHATEVER", r"unknown feature token\(s\) \['WHATEVER'\]"),
    ],
)
def test_interpret_rejects(tag: str, features: str, message: str) -> None:
    with pytest.raises(PipelineError, match=message):
        interpret(seg(tag, features))
