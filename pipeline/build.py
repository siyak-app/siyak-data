"""``build``: core.db plus one file per pack, written to dist/.

Each SQLite pack is written as ``<id>.sqlite`` (kept for inspection and
validation) and compressed to ``<id>.sqlite.zst``, the file that is published.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.build_core import build_core, load_tanzil
from pipeline.build_morphology import build_morphology_pack
from pipeline.build_tafsir import build_tafsir_pack, is_available, is_tafsir_source, write_reports
from pipeline.build_translation import build_translation_pack, verse_ids
from pipeline.compress import compress_pack
from pipeline.errors import PipelineError
from pipeline.paths import dist_dir
from pipeline.schema import build_epoch, build_timestamp
from pipeline.sources import Source, load_all

TANZIL = "tanzil"


def translation_sources(sources: list[Source]) -> list[Source]:
    """Sources whose ``[pack]`` is a translation, sorted by pack id."""
    found = [s for s in sources if s.pack is not None and s.pack.type == "translation"]
    return sorted(found, key=lambda s: s.pack.id if s.pack else "")


def morphology_sources(sources: list[Source]) -> list[Source]:
    """Sources whose ``[pack]`` is a morphology pack, sorted by pack id."""
    found = [s for s in sources if s.pack is not None and s.pack.type == "morphology"]
    return sorted(found, key=lambda s: s.pack.id if s.pack else "")


def tafsir_sources(sources: list[Source]) -> list[Source]:
    """Sources whose ``[pack]`` is a Quranpedia or QUL tafsir, sorted by pack id."""
    found = [s for s in sources if is_tafsir_source(s)]
    return sorted(found, key=lambda s: s.pack.id if s.pack else "")


def run_build() -> list[Path]:
    """Build everything and return the written files."""
    sources = load_all()
    tanzil = next((s for s in sources if s.id == TANZIL), None)
    if tanzil is None:
        raise PipelineError("no 'tanzil' source found")
    built_at = build_timestamp()
    out = dist_dir()
    out.mkdir(parents=True, exist_ok=True)
    translations = translation_sources(sources)
    bundled = [s for s in translations if s.pack is not None and s.pack.bundled]
    written = [build_core(out / "core.db", tanzil=tanzil, bundled=bundled, built_at=built_at)]
    inputs = load_tanzil(tanzil)
    ids = verse_ids(inputs.metadata)
    for source in translations:
        sqlite_path = build_translation_pack(source, ids, out, built_at)
        written += [sqlite_path, compress_pack(sqlite_path)]
    verses = {(a.surah, a.ayah): a.text for a in inputs.uthmani.verses}
    for source in morphology_sources(sources):
        written += build_morphology_pack(
            source, verses, ids, out, built_at=built_at, mtime=build_epoch()
        )
    clean = {(a.surah, a.ayah): a.text for a in inputs.clean.verses}
    for source in tafsir_sources(sources):
        if not is_available(source):
            continue
        sqlite_path = build_tafsir_pack(source, ids, clean, out, built_at)
        written += [sqlite_path, compress_pack(sqlite_path)]
    write_reports(out)
    return written
