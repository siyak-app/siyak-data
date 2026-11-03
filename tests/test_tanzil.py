from pathlib import Path

import pytest

from pipeline.errors import PipelineError
from pipeline.normalize import normalize
from pipeline.tanzil import parse_metadata, parse_quran_xml, parse_translation

CACHE = Path(__file__).parent / "fixtures" / "cache"


SHADDA = "\u0651"


def test_quran_xml_keeps_basmala_apart() -> None:
    text = parse_quran_xml(CACHE / "tanzil" / "quran-uthmani.xml")
    verses = {(a.surah, a.ayah): a for a in text.verses}
    assert verses[(1, 1)].bismillah is None
    assert normalize(verses[(1, 1)].text) == "بسم الله الرحمن الرحيم"
    assert normalize(verses[(112, 1)].text) == "قل هو الله احد"
    assert verses[(112, 1)].bismillah == verses[(1, 1)].text
    # Surah 97's basmala carries a shadda on its first letter in the Uthmani text.
    variant = verses[(97, 1)].bismillah
    assert variant is not None
    assert variant != verses[(1, 1)].text
    assert SHADDA in variant.split(" ")[0]
    assert normalize(variant) == "بسم الله الرحمن الرحيم"


def test_notice_is_the_verbatim_copyright_block() -> None:
    notice = parse_quran_xml(CACHE / "tanzil" / "quran-simple-clean.xml").notice
    assert notice.startswith("# PLEASE DO NOT REMOVE OR CHANGE THIS COPYRIGHT BLOCK")
    assert "CHANGING IT IS NOT ALLOWED." in notice
    assert notice.endswith("#" + "=" * 68)


def test_metadata_and_juz() -> None:
    meta = parse_metadata(CACHE / "tanzil" / "quran-data.xml")
    assert len(meta.surahs) == 114
    assert sum(s.ayah_count for s in meta.surahs) == 6236
    assert meta.surahs[0].name_translit == "Al-Faatiha"
    assert meta.surahs[1].revelation_type == "medinan"
    juz = meta.juz_of()
    assert (juz[(2, 141)], juz[(2, 142)]) == (1, 2)
    assert (juz[(77, 50)], juz[(78, 1)], juz[(114, 6)]) == (29, 30, 30)


def test_translation_parser(tmp_path: Path) -> None:
    parsed = parse_translation(CACHE / "en.pickthall" / "en.pickthall.txt")
    assert parsed.verses[(112, 1)] == "Say: He is Allah, the One!"
    assert "Translator: Mohammed Marmaduke William Pickthall" in parsed.header

    bad = tmp_path / "bad.txt"
    bad.write_text("1|1|a\n1|1|b\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="duplicate verse 1:1"):
        parse_translation(bad)
    bad.write_text("1-1-a\n", encoding="utf-8")
    with pytest.raises(PipelineError, match=r"not a 'surah\|ayah\|text' line"):
        parse_translation(bad)
    bad.write_text(" a\n", encoding="utf-8")
    with pytest.raises(PipelineError, match=r"not a 'surah\|ayah\|text' line"):
        parse_translation(bad)


def test_translation_parser_joins_continuation_lines(tmp_path: Path) -> None:
    path = tmp_path / "t.txt"
    path.write_text("1|1|one, \n two, \n three\n1|2|next\n", encoding="utf-8")
    assert parse_translation(path).verses == {(1, 1): "one,  two,  three", (1, 2): "next"}
