"""``manifest.json`` (spec §6.3) from the built packs and their ``source.toml``.

Each pack entry combines the ``[pack]`` metadata with the size and sha256 of
the published (compressed) file and its ``installed_size`` (decompressed
bytes). Packs with ``publish = false`` are built and validated but never
written here. Bundle members that are not part of this release are dropped
with a warning, and a bundle left empty is omitted.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from pipeline.archive import extract_archive
from pipeline.build_audio import prebuilt
from pipeline.build_translation import require_pack
from pipeline.compress import MAX_PACK_SIZE, decompress_pack, frame_content_size
from pipeline.errors import PipelineError
from pipeline.fetch import sha256_file
from pipeline.install import ARCHIVE_LAYOUT
from pipeline.paths import repo_root
from pipeline.schema import build_timestamp, read_pack_info
from pipeline.sources import Source

#: File name of each pack type in a release (spec §6.1).
PACK_FILE = {
    "translation": "{id}.sqlite.zst",
    "tafsir": "{id}.sqlite.zst",
    "morphology": "{id}.tar.zst",
    "vectors": "{id}.sqlite.zst",
    "model": "{id}.tar.zst",
    "audio": "{id}.tar.zst",
}
DEV_TAG = "data-dev"


def pack_file_name(source: Source) -> str:
    """The release asset name of a source's pack."""
    pack = require_pack(source)
    pattern = PACK_FILE.get(pack.type)
    if pattern is None:
        raise PipelineError(f"no file name rule for pack type '{pack.type}'")
    return pattern.format(id=pack.id)


def pack_entry(source: Source, path: Path, url: str) -> dict[str, Any]:
    """The manifest entry of one built pack."""
    pack = require_pack(source)
    with tempfile.TemporaryDirectory(prefix="siyak-manifest-") as tmp:
        layout = ARCHIVE_LAYOUT.get(pack.type)
        if layout is None:
            database = decompress_pack(path, Path(tmp) / "pack.sqlite", MAX_PACK_SIZE)
            installed_size = database.stat().st_size
        else:
            db_member, members = layout
            files = extract_archive(path, Path(tmp), expected=set(members), max_size=MAX_PACK_SIZE)
            database = files[db_member]
            installed_size = frame_content_size(path)
        with closing(sqlite3.connect(database)) as conn:
            info = read_pack_info(conn)
    if (info.id, info.version) != (pack.id, pack.version):
        raise PipelineError(
            f"{path.name}: built as {info.id} {info.version}, source.toml says "
            f"{pack.id} {pack.version}; rebuild"
        )
    return _entry(source, path.stat().st_size, installed_size, sha256_file(path), url)


def prebuilt_entry(source: Source, pin: dict[str, Any], url: str) -> dict[str, Any]:
    """The manifest entry of a pack pinned as a release asset (``[build.prebuilt]``),
    written from the pin without downloading the pack (pack-format §6)."""
    return _entry(source, int(pin["size"]), int(pin["installed_size"]), str(pin["sha256"]), url)


def _entry(source: Source, size: int, installed_size: int, sha256: str, url: str) -> dict[str, Any]:
    pack = require_pack(source)
    entry: dict[str, Any] = {
        "id": pack.id,
        "type": pack.type,
        "lang": pack.lang,
        "title": pack.title,
        "author": pack.author,
        "version": pack.version,
        "min_app_version": pack.min_app_version,
        "size": size,
        "installed_size": installed_size,
        "sha256": sha256,
        "url": url,
        "license": pack.license,
        "license_terms": pack.license_terms,
        "attribution": pack.attribution,
        "citation": pack.citation,
    }
    if pack.description:
        entry["description"] = pack.description
    if pack.meta:
        entry["meta"] = pack.meta
    if pack.requires:
        entry["requires"] = list(pack.requires)
    if pack.terms_ack:
        entry["terms_ack"] = True
    return entry


def _listed(source: Source, path: Path, unpublished: bool, warnings: list[str]) -> bool:
    """Whether a pack goes into the manifest; raise if a published pack cannot."""
    pack = require_pack(source)
    if not pack.publish and not unpublished:
        warnings.append(f"{pack.id}: publish = false, not in the manifest")
        return False
    if not path.exists():
        if unpublished:  # local testing lists what is built
            warnings.append(f"{pack.id}: not built, not in the manifest")
            return False
        raise PipelineError(f"{path}: not built; run 'siyak-data build'")
    if not pack.publish:
        warnings.append(f"{pack.id}: publish = false, listed for local testing only")
        return True
    problem = source.permission_problem()
    if problem:
        raise PipelineError(problem)
    return True


def _manifest_entry(
    source: Source,
    dist: Path,
    *,
    base: dict[str, Any],
    tag: str,
    unpublished: bool,
    warnings: list[str],
) -> dict[str, Any] | None:
    """The entry of one pack, or None when it is not part of this manifest."""
    name = pack_file_name(source)
    path = dist / name
    pack = require_pack(source)
    pin = prebuilt(source) if pack.type == "audio" else None
    if pack.type == "audio" and not path.exists():
        # Audio packs are built by a maintainer and pinned, never in the release workflow.
        if pin is None:
            warnings.append(f"{pack.id}: no [build.prebuilt] and not built, not in the manifest")
            return None
        if not pack.publish and not unpublished:
            warnings.append(f"{pack.id}: publish = false, not in the manifest")
            return None
        url = base["release_download_url"].format(tag=pin["tag"], file=name)
        return prebuilt_entry(source, pin, url)
    if not _listed(source, path, unpublished, warnings):
        return None
    if pin is not None and tag != DEV_TAG:
        # A local copy of a pinned pack: the release still points at the pinned asset.
        if sha256_file(path) != pin["sha256"]:
            raise PipelineError(f"{path}: differs from the pinned {pin['tag']} asset")
        url = base["release_download_url"].format(tag=pin["tag"], file=name)
        return prebuilt_entry(source, pin, url)
    url = base["release_download_url"].format(tag=tag, file=name)
    return pack_entry(source, path, url)


def build_manifest(
    sources: list[Source],
    dist: Path,
    *,
    tag: str | None = None,
    template: Path | None = None,
    unpublished: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Return the manifest and a list of warnings.

    ``unpublished`` lists every built pack, ``publish = false`` ones included, and skips
    unbuilt ones, for trying packs in a debug build (``SIYAK_PACK_SOURCE``); it is refused
    for a release tag.
    """
    tag = tag or os.environ.get("SIYAK_DATA_TAG") or DEV_TAG
    if unpublished and tag != DEV_TAG:
        raise PipelineError("--unpublished is for local testing; it cannot be used with a tag")
    base = json.loads(
        (template or repo_root() / "manifest.template.json").read_text(encoding="utf-8")
    )
    warnings: list[str] = []
    if tag == DEV_TAG:
        warnings.append(f"SIYAK_DATA_TAG is not set; pack URLs use '{DEV_TAG}'")
    packs = []
    for source in sorted(
        (s for s in sources if s.pack is not None), key=lambda s: require_pack(s).id
    ):
        entry = _manifest_entry(
            source, dist, base=base, tag=tag, unpublished=unpublished, warnings=warnings
        )
        if entry is not None:
            packs.append(entry)
    published = {p["id"] for p in packs}
    bundles = []
    for bundle in base.get("bundles", []):
        members = [p for p in bundle["packs"] if p in published]
        dropped = [p for p in bundle["packs"] if p not in published]
        if dropped:
            warnings.append(f"bundle '{bundle['id']}': not in this release: {', '.join(dropped)}")
        if members:
            bundles.append({**bundle, "packs": members})
        else:
            warnings.append(f"bundle '{bundle['id']}' is empty and omitted")
    manifest = {
        "schema_version": base["schema_version"],
        "generated_at": build_timestamp(),
        "pricing_url": base["pricing_url"],
        "packs": packs,
        "bundles": bundles,
    }
    return manifest, warnings


def write_manifest(manifest: dict[str, Any], out: Path) -> Path:
    """Write the manifest as pretty-printed UTF-8 JSON."""
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out
