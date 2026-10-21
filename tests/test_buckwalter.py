from pathlib import Path

import pytest

from pipeline.buckwalter import TABLE, root_to_arabic, to_arabic, to_buckwalter
from pipeline.errors import PipelineError
from pipeline.qac import parse_qac

QAC_FILE = (
    Path(__file__).parent.parent
    / ".cache"
    / "morphology.qac"
    / ("quranic-corpus-morphology-0.4.txt")
)


def test_table_is_a_bijection() -> None:
    assert len(TABLE) == 60
    assert len(set(TABLE.values())) == len(TABLE)


@pytest.mark.parametrize(("latin", "arabic"), sorted(TABLE.items()))
def test_every_symbol_round_trips(latin: str, arabic: str) -> None:
    assert to_arabic(latin) == arabic
    assert to_buckwalter(arabic) == latin


def test_words_and_roots() -> None:
    assert to_arabic("kataba") == "كَتَبَ"
    assert to_arabic("{l") == "ٱل"
    assert root_to_arabic("qwl") == "ق و ل"
    assert root_to_arabic("'mn") == "ء م ن"


def test_unknown_character_is_an_error() -> None:
    with pytest.raises(PipelineError, match=r"unknown Buckwalter character '\?'"):
        to_arabic("ka?aba")
    with pytest.raises(PipelineError, match="no Buckwalter character for U\\+06D6"):
        to_buckwalter("ۖ")


@pytest.mark.full
def test_every_character_of_the_qac_file_is_mapped() -> None:
    if not QAC_FILE.exists():
        pytest.skip("QAC file not in .cache/")
    used: set[str] = set()
    for seg in parse_qac(QAC_FILE).segments:
        used.update(seg.form)
        for token in seg.features:
            if token.startswith(("LEM:", "ROOT:")):
                used.update(token.split(":", 1)[1])
    assert used - set(TABLE) == set()
