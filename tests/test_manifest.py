import dataclasses
import json
from pathlib import Path

import pytest

from pipeline.build_pricing import build_pricing
from pipeline.errors import PipelineError
from pipeline.manifest import DEV_TAG, build_manifest
from pipeline.sources import load_all

SPEC_PACK_KEYS = {
    "id", "type", "lang", "title", "author", "version", "min_app_version", "size",
    "installed_size", "sha256", "url", "license", "license_terms", "attribution", "citation",
}  # fmt: skip


def test_manifest_shape(built_fixtures: Path, fixture_sources: None) -> None:
    manifest, warnings = build_manifest(load_all(), built_fixtures, tag="data-2026.10.0")
    assert set(manifest) == {"schema_version", "generated_at", "pricing_url", "packs", "bundles"}
    packs = {p["id"]: p for p in manifest["packs"]}
    assert sorted(packs) == ["ar.jalalayn", "ar.razi", "en.pickthall", "morphology.qac"]
    entry = packs["en.pickthall"]
    assert set(entry) == SPEC_PACK_KEYS
    assert entry["url"].endswith("/download/data-2026.10.0/en.pickthall.sqlite.zst")
    assert entry["title"] == {
        "tr": "Pickthall İngilizce Meali",
        "en": "The Meaning of the Glorious Koran",
    }
    assert entry["size"] == (built_fixtures / "en.pickthall.sqlite.zst").stat().st_size
    assert entry["installed_size"] == (built_fixtures / "en.pickthall.sqlite").stat().st_size
    assert entry["size"] < entry["installed_size"]
    morphology = packs["morphology.qac"]
    assert morphology["url"].endswith("/download/data-2026.10.0/morphology.qac.tar.zst")
    assert morphology["size"] < morphology["installed_size"]
    tafsir = packs["ar.jalalayn"]
    assert set(tafsir) == SPEC_PACK_KEYS | {"description"}
    assert tafsir["type"] == "tafsir"
    assert set(tafsir["description"]) == {"tr", "en"}
    assert tafsir["url"].endswith("/download/data-2026.10.0/ar.jalalayn.sqlite.zst")
    assert (
        tafsir["attribution"] == "Source: Quranpedia.net · dump 2026-10-20 (https://quranpedia.net)"
    )
    assert tafsir["installed_size"] == (built_fixtures / "ar.jalalayn.sqlite").stat().st_size
    assert [(b["id"], b["packs"]) for b in manifest["bundles"]] == [
        ("recommended", ["morphology.qac", "ar.jalalayn"])
    ]
    assert not warnings


def test_unpublished_pack_is_left_out(built_fixtures: Path, fixture_sources: None) -> None:
    sources = load_all()
    hidden = [
        dataclasses.replace(s, pack=dataclasses.replace(s.pack, publish=False)) if s.pack else s
        for s in sources
    ]
    manifest, warnings = build_manifest(hidden, built_fixtures, tag="t")
    assert manifest["packs"] == []
    assert any("publish = false" in w for w in warnings)
    # For a debug build they can be listed, but never in a release.
    manifest, warnings = build_manifest(hidden, built_fixtures, tag=DEV_TAG, unpublished=True)
    assert {"morphology.qac", "ar.jalalayn", "ar.razi"} <= {p["id"] for p in manifest["packs"]}
    assert any("local testing only" in w for w in warnings)
    with pytest.raises(PipelineError, match="local testing"):
        build_manifest(hidden, built_fixtures, tag="t", unpublished=True)


def test_version_mismatch_requires_rebuild(built_fixtures: Path, fixture_sources: None) -> None:
    bumped = [
        dataclasses.replace(s, pack=dataclasses.replace(s.pack, version="9.9.9")) if s.pack else s
        for s in load_all()
    ]
    with pytest.raises(PipelineError, match="rebuild"):
        build_manifest(bumped, built_fixtures, tag="t")


def test_pricing_placeholder(tmp_path: Path) -> None:
    out = build_pricing(tmp_path / "pricing.json")
    assert json.loads(out.read_text(encoding="utf-8")) == {
        "updated_at": "2026-10-21",
        "currency": "USD",
        "models": {},
    }


def test_publishing_without_required_permission_is_refused(
    built_fixtures: Path, fixture_sources: None, tmp_path: Path
) -> None:
    sources = load_all()
    gated = [
        dataclasses.replace(
            s, path=tmp_path / s.id / "source.toml", extra={**s.extra, "requires_permission": True}
        )
        if s.id == "ar.jalalayn"
        else s
        for s in sources
    ]
    with pytest.raises(PipelineError, match=r"needs PERMISSION\.md"):
        build_manifest(gated, built_fixtures, tag="t")
    (tmp_path / "ar.jalalayn").mkdir()
    (tmp_path / "ar.jalalayn" / "PERMISSION.md").write_text("reply", encoding="utf-8")
    manifest, _ = build_manifest(gated, built_fixtures, tag="t")
    assert "ar.jalalayn" in {p["id"] for p in manifest["packs"]}
