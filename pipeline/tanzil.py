"""Parsers for Tanzil files: Quran text (XML export), metadata and translations.

Parsing changes nothing: every text is returned exactly as it appears in the
file. The Quran text comes from Tanzil's XML export because it keeps the
basmala of surahs 2–114 (except 9) in a separate ``bismillah`` attribute,
while the plain-text export prefixes it to ayah 1.

The input files are pinned by sha256 before they reach these functions, so
``xml.etree`` (which does not resolve external entities) is safe to use.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from pipeline.errors import PipelineError


@dataclass(frozen=True)
class Aya:
    """One verse of a Tanzil text."""

    surah: int
    ayah: int
    text: str
    bismillah: str | None


@dataclass(frozen=True)
class QuranText:
    """A Tanzil Quran text: verses in order plus the verbatim copyright block."""

    notice: str
    verses: list[Aya]


@dataclass(frozen=True)
class SurahMeta:
    """One ``<sura>`` entry of quran-data.xml."""

    number: int
    ayah_count: int
    name_ar: str
    name_translit: str
    name_en: str
    revelation_type: str  # 'meccan' or 'medinan'


@dataclass(frozen=True)
class Metadata:
    """quran-data.xml: surahs, juz start points and the file's attributes."""

    version: str
    copyright: str
    license: str
    surahs: list[SurahMeta]
    juz_starts: list[tuple[int, int, int]]  # (juz, surah, ayah)

    def juz_of(self) -> dict[tuple[int, int], int]:
        """Map every (surah, ayah) to its juz, using the juz start points."""
        starts = sorted(self.juz_starts, key=lambda j: (j[1], j[2]))
        result: dict[tuple[int, int], int] = {}
        current = 0
        index = 0
        for surah in self.surahs:
            for ayah in range(1, surah.ayah_count + 1):
                while index < len(starts) and (starts[index][1], starts[index][2]) <= (
                    surah.number,
                    ayah,
                ):
                    current = starts[index][0]
                    index += 1
                result[(surah.number, ayah)] = current
        return result


def _attr(element: ET.Element, name: str, where: str) -> str:
    value = element.get(name)
    if value is None:
        raise PipelineError(f"{where}: <{element.tag}> has no '{name}' attribute")
    return value


def _int_attr(element: ET.Element, name: str, where: str) -> int:
    raw = _attr(element, name, where)
    try:
        return int(raw)
    except ValueError as exc:
        raise PipelineError(f"{where}: '{name}' is not an integer: {raw!r}") from exc


def parse_quran_xml(path: Path) -> QuranText:
    """Parse a Tanzil Quran text in XML format (``outType=xml``)."""
    raw = path.read_text(encoding="utf-8")
    root = ET.fromstring(raw)
    if root.tag != "quran":
        raise PipelineError(f"{path}: root element is <{root.tag}>, expected <quran>")
    # The copyright block is the single comment before <quran>.
    prolog = raw[: raw.find("<quran")]
    start, end = prolog.find("<!--"), prolog.find("-->")
    if start < 0 or end < start or prolog.count("<!--") != 1:
        raise PipelineError(f"{path}: expected exactly one comment block before <quran>")
    notice = prolog[start + 4 : end].strip("\r\n\t ")
    verses: list[Aya] = []
    for sura in root.iter("sura"):
        surah = _int_attr(sura, "index", str(path))
        for aya in sura.iter("aya"):
            where = f"{path} {surah}:{aya.get('index')}"
            verses.append(
                Aya(
                    surah=surah,
                    ayah=_int_attr(aya, "index", where),
                    text=_attr(aya, "text", where),
                    bismillah=aya.get("bismillah"),
                )
            )
    return QuranText(notice=notice, verses=verses)


def parse_metadata(path: Path) -> Metadata:
    """Parse Tanzil's quran-data.xml."""
    root = ET.parse(path).getroot()
    where = str(path)
    surahs: list[SurahMeta] = []
    for sura in root.iter("sura"):
        kind = _attr(sura, "type", where).lower()
        if kind not in ("meccan", "medinan"):
            raise PipelineError(f"{where}: sura {sura.get('index')} has type {kind!r}")
        surahs.append(
            SurahMeta(
                number=_int_attr(sura, "index", where),
                ayah_count=_int_attr(sura, "ayas", where),
                name_ar=_attr(sura, "name", where),
                name_translit=_attr(sura, "tname", where),
                name_en=_attr(sura, "ename", where),
                revelation_type=kind,
            )
        )
    juz_starts = [
        (
            _int_attr(j, "index", where),
            _int_attr(j, "sura", where),
            _int_attr(j, "aya", where),
        )
        for j in root.iter("juz")
    ]
    return Metadata(
        version=root.get("version", ""),
        copyright=root.get("copyright", ""),
        license=root.get("license", ""),
        surahs=surahs,
        juz_starts=juz_starts,
    )


@dataclass(frozen=True)
class Translation:
    """A Tanzil translation file (``surah|ayah|text`` lines plus a ``#`` header)."""

    header: str
    verses: dict[tuple[int, int], str]


def parse_translation(path: Path) -> Translation:
    """Parse a Tanzil translation text file; reject malformed or duplicate lines."""
    verses: dict[tuple[int, int], str] = {}
    header: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("#"):
            header.append(line)
            continue
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            raise PipelineError(f"{path}:{number}: not a 'surah|ayah|text' line: {line[:60]!r}")
        key = (int(parts[0]), int(parts[1]))
        if key in verses:
            raise PipelineError(f"{path}:{number}: duplicate verse {key[0]}:{key[1]}")
        verses[key] = parts[2]
    return Translation(header="\n".join(header), verses=verses)
