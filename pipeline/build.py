"""``build``: core.db plus one file per pack, written to dist/."""

from __future__ import annotations

from pathlib import Path

from pipeline.build_core import build_core, load_tanzil
from pipeline.build_translation import build_translation_pack, verse_ids
from pipeline.errors import PipelineError
from pipeline.paths import dist_dir
from pipeline.schema import build_timestamp
from pipeline.sources import Source, load_all

TANZIL = "tanzil"


def translation_sources(sources: list[Source]) -> list[Source]:
    """Sources whose ``[pack]`` is a translation, sorted by pack id."""
    found = [s for s in sources if s.pack is not None and s.pack.type == "translation"]
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
    ids = verse_ids(load_tanzil(tanzil).metadata)
    written += [build_translation_pack(s, ids, out, built_at) for s in translations]
    return written
