"""Pinned verse vectors (pack-format §4.7): a release builds vector packs from them."""

from pathlib import Path

import pytest

from pipeline.build_embeddings import (
    build_vector_pack,
    check_agreement,
    export_vectors,
    load_prebuilt,
)
from pipeline.embedding import VERSE_COUNT
from pipeline.errors import PipelineError
from pipeline.fetch import sha256_file
from pipeline.manifest import pack_entry
from pipeline.sources import Source, load_source

API_PACK = """
[source]
id = "vectors.api-test"
name = "test"
homepage = "https://example.org"
license = "x"
attribution = "x"

[[files]]
name = "vectors.npy"
url = "https://example.org/vector-inputs/vectors.api-test-{version}.npy"
version = "1.0.0"
sha256 = "{sha}"

[build]
text = "ar+tr+en"

[pack]
id = "vectors.api-test"
type = "vectors"
lang = "mul"
title = {{ tr = "t", en = "t" }}
author = "a"
version = "1.0.0"
license = "x"
requires = []
publish = false
terms_ack = true

[pack.license_terms]
tr = ["Aramalar Voyage AI'a gönderilir."]
en = ["Searches are sent to Voyage AI."]

[pack.meta]
embedding_model = "voyage/voyage-4-large"
dim = 4
normalized = true
source_text = "x"
backend = "api"
provider = "voyage"
api_model = "voyage-4-large"
api_dimensions = 4
"""


def pinned_source(tmp_path: Path, sha: str, version: str = "1.0.0") -> Source:
    path = tmp_path / "src" / "source.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(API_PACK.format(sha=sha, version=version), encoding="utf-8")
    return load_source(path)


def test_an_api_pack_is_built_from_pinned_vectors_without_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    np = pytest.importorskip("numpy")
    monkeypatch.setenv("SIYAK_DATA_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("VOYAGE_API", raising=False)
    vectors = np.zeros((VERSE_COUNT, 4), dtype="<f4")
    vectors[np.arange(VERSE_COUNT), np.arange(VERSE_COUNT) % 4] = 1
    file = tmp_path / "v.npy"
    np.save(file, vectors, allow_pickle=False)
    source = pinned_source(tmp_path, sha256_file(file))
    cached = source.cache_path("vectors.npy")
    cached.parent.mkdir(parents=True)
    cached.write_bytes(file.read_bytes())

    out = tmp_path / "dist"
    out.mkdir()
    paths = build_vector_pack(source, {}, out, built_at="2026-01-01T00:00:00Z")
    assert [p.name for p in paths] == ["vectors.api-test.sqlite", "vectors.api-test.sqlite.zst"]

    entry = pack_entry(source, paths[1], "https://example.org/p")
    assert entry["terms_ack"] is True, "the app asks before installing"
    assert entry["meta"]["provider"] == "voyage"

    # export-vectors gives back the very same file.
    exported, sha = export_vectors(source, out, tmp_path / "inputs")
    assert exported.name == "vectors.api-test-1.0.0.npy"
    assert sha == sha256_file(file)

    cached.write_bytes(b"changed")
    with pytest.raises(PipelineError, match="sha256"):
        load_prebuilt(source)


def test_pinned_vectors_belong_to_one_pack_version(tmp_path: Path) -> None:
    source = pinned_source(tmp_path, "00", version="0.9.0")
    with pytest.raises(PipelineError, match=r"another pack version \(want vectors.api-test-1.0.0"):
        load_prebuilt(source)


def test_pinned_local_vectors_must_match_the_model_pack() -> None:
    np = pytest.importorskip("numpy")
    a = np.eye(4, dtype=np.float32)
    check_agreement(a, a.copy(), "x")
    b = a.copy()
    b[2] = [0, 0.6, 0.8, 0]
    with pytest.raises(PipelineError, match="differ from the model pack"):
        check_agreement(a, b, "x")


def test_terms_ack_needs_terms(tmp_path: Path) -> None:
    text = API_PACK.format(sha="00", version="1.0.0")
    start = text.index("[pack.license_terms]")
    path = tmp_path / "source.toml"
    path.write_text(text[:start] + text[text.index("[pack.meta]") :], encoding="utf-8")
    with pytest.raises(PipelineError, match="terms_ack needs"):
        load_source(path)
