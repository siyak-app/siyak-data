"""Loading and checking ``sources/**/source.toml``.

Every data source is described by one ``source.toml``: where its files come
from, their pinned sha256, the license and attribution, and, for sources that
become a pack, the pack metadata used for ``pack_info`` and the manifest
(docs/adding-a-source.md describes every field).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.errors import PipelineError
from pipeline.paths import cache_dir, sources_dir

PACK_TYPES = ("translation", "tafsir", "morphology", "vectors", "model")


@dataclass(frozen=True)
class SourceFile:
    """One downloadable file of a source, pinned by sha256."""

    name: str
    url: str
    version: str
    sha256: str
    note: str = ""
    #: Optional copy of the exact pinned bytes (a siyak-data release asset).
    mirror: str = ""


@dataclass(frozen=True)
class Terms:
    """Terms of use as stated by the source, and who accepted them for this project."""

    text: str
    url: str
    accepted_by: str = ""
    accepted_on: str = ""


@dataclass(frozen=True)
class PackMeta:
    """Metadata for a pack built from this source (``[pack]`` table)."""

    id: str
    type: str
    lang: str
    title: dict[str, str]
    author: str
    version: str
    min_app_version: str
    license: str
    attribution: str | None
    license_terms: dict[str, list[str]] | None
    citation: dict[str, str]
    meta: dict[str, Any]
    publish: bool
    description: dict[str, str] | None = None
    #: Also included in core.db (spec §6.2).
    bundled: bool = False


@dataclass(frozen=True)
class Source:
    """A parsed ``source.toml``."""

    id: str
    name: str
    homepage: str
    license: str
    attribution: str
    path: Path
    files: tuple[SourceFile, ...]
    terms: Terms | None = None
    pack: PackMeta | None = None
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def cache_path(self, file_name: str) -> Path:
        """Where ``fetch`` stores the given file of this source."""
        return cache_dir() / self.id / file_name

    def file(self, name: str) -> SourceFile:
        """Return the file entry called ``name``."""
        for f in self.files:
            if f.name == name:
                return f
        raise PipelineError(f"{self.path}: no [[files]] entry named '{name}'")


def _require(table: dict[str, Any], key: str, where: str) -> Any:
    if key not in table:
        raise PipelineError(f"{where}: missing required key '{key}'")
    return table[key]


def _str(table: dict[str, Any], key: str, where: str) -> str:
    value = _require(table, key, where)
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"{where}: '{key}' must be a non-empty string")
    return value


def _parse_pack(raw: dict[str, Any], where: str) -> PackMeta:
    pack_type = _str(raw, "type", where)
    if pack_type not in PACK_TYPES:
        raise PipelineError(f"{where}: type '{pack_type}' is not one of {PACK_TYPES}")
    title = _require(raw, "title", where)
    if not isinstance(title, dict) or set(title) != {"tr", "en"}:
        raise PipelineError(f"{where}: title must be a table with exactly 'tr' and 'en'")
    publish = _require(raw, "publish", where)
    if not isinstance(publish, bool):
        raise PipelineError(f"{where}: publish must be true or false")
    terms = raw.get("license_terms")
    if terms is not None and (not isinstance(terms, dict) or set(terms) != {"tr", "en"}):
        raise PipelineError(f"{where}: license_terms must have exactly 'tr' and 'en' lists")
    return PackMeta(
        id=_str(raw, "id", where),
        type=pack_type,
        lang=_str(raw, "lang", where),
        title=dict(title),
        author=_str(raw, "author", where),
        version=_str(raw, "version", where),
        min_app_version=str(raw.get("min_app_version", "0.1.0")),
        license=_str(raw, "license", where),
        attribution=raw.get("attribution"),
        license_terms=terms,
        citation=dict(raw.get("citation", {})),
        meta=dict(raw.get("meta", {})),
        publish=publish,
        description=raw.get("description"),
        bundled=bool(raw.get("bundled", False)),
    )


def load_source(path: Path) -> Source:
    """Parse one ``source.toml``; raise ``PipelineError`` with the file path on any problem."""
    where = str(path)
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    src = _require(data, "source", where)
    files = tuple(
        SourceFile(
            name=_str(f, "name", f"{where} [[files]]"),
            url=_str(f, "url", f"{where} [[files]]"),
            version=_str(f, "version", f"{where} [[files]]"),
            sha256=str(f.get("sha256", "")).lower(),
            note=str(f.get("note", "")),
            mirror=str(f.get("mirror", "")),
        )
        for f in data.get("files", [])
    )
    if len({f.name for f in files}) != len(files):
        raise PipelineError(f"{where}: duplicate file names in [[files]]")
    terms_raw = src.get("terms")
    terms = (
        Terms(
            text=_str(terms_raw, "text", f"{where} [source.terms]"),
            url=_str(terms_raw, "url", f"{where} [source.terms]"),
            accepted_by=str(terms_raw.get("accepted_by", "")),
            accepted_on=str(terms_raw.get("accepted_on", "")),
        )
        if terms_raw
        else None
    )
    pack = _parse_pack(data["pack"], f"{where} [pack]") if "pack" in data else None
    return Source(
        id=_str(src, "id", where),
        name=_str(src, "name", where),
        homepage=_str(src, "homepage", where),
        license=_str(src, "license", where),
        attribution=_str(src, "attribution", where),
        path=path,
        files=files,
        terms=terms,
        pack=pack,
        notes=str(src.get("notes", "")),
    )


def load_all(root: Path | None = None) -> list[Source]:
    """Load every ``source.toml`` below ``sources/``, sorted by source id."""
    base = root or sources_dir()
    sources = [load_source(p) for p in sorted(base.rglob("source.toml"))]
    ids = [s.id for s in sources]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise PipelineError(f"duplicate source ids: {sorted(duplicates)}")
    return sorted(sources, key=lambda s: s.id)


def get_source(source_id: str, root: Path | None = None) -> Source:
    """Return the source with the given id."""
    for s in load_all(root):
        if s.id == source_id:
            return s
    raise PipelineError(f"unknown source '{source_id}'")
