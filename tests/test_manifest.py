import dataclasses
import json
from pathlib import Path

import pytest

from pipeline.build_pricing import build_pricing
from pipeline.errors import PipelineError
from pipeline.manifest import build_manifest
from pipeline.sources import load_all

SPEC_PACK_KEYS = {
    "id", "type", "lang", "title", "author", "version", "min_app_version", "size",
    "sha256", "url", "license", "license_terms", "attribution", "citation",
}  # fmt: skip


def test_manifest_shape(built_fixtures: Path, fixture_sources: None) -> None:
    manifest, warnings = build_manifest(load_all(), built_fixtures, tag="data-2026.10.0")
    assert set(manifest) == {"schema_version", "generated_at", "pricing_url", "packs", "bundles"}
    (entry,) = manifest["packs"]
    assert set(entry) == SPEC_PACK_KEYS
    assert entry["url"].endswith("/download/data-2026.10.0/en.pickthall.sqlite")
    assert entry["title"] == {
        "tr": "Pickthall İngilizce Meali",
        "en": "The Meaning of the Glorious Koran",
    }
    assert entry["size"] == (built_fixtures / "en.pickthall.sqlite").stat().st_size
    assert manifest["bundles"] == []  # morphology.qac and ar.jalalayn come in M1b/M1c
    assert any("recommended" in w for w in warnings)


def test_unpublished_pack_is_left_out(built_fixtures: Path, fixture_sources: None) -> None:
    sources = load_all()
    hidden = [
        dataclasses.replace(s, pack=dataclasses.replace(s.pack, publish=False)) if s.pack else s
        for s in sources
    ]
    manifest, warnings = build_manifest(hidden, built_fixtures, tag="t")
    assert manifest["packs"] == []
    assert any("publish = false" in w for w in warnings)


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
