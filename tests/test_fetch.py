import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from pipeline import fetch
from pipeline.errors import PipelineError
from pipeline.fetch import fetch_file, verify_cached
from pipeline.sources import Source, SourceFile, load_source

CONTENT = b"1|1|test\n"
DIGEST = hashlib.sha256(CONTENT).hexdigest()


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SIYAK_DATA_ROOT", str(tmp_path))
    return tmp_path


def make_source(sha: str) -> Source:
    return Source(
        id="demo",
        name="Demo",
        homepage="https://example.org",
        license="test",
        attribution="test",
        path=Path("sources/demo/source.toml"),
        files=(SourceFile("a.txt", "https://example.invalid/a.txt", "1", sha),),
    )


def put_cached(root: Path, data: bytes) -> Path:
    path = root / ".cache" / "demo" / "a.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    return path


def test_cached_file_with_matching_hash_is_accepted(root: Path) -> None:
    put_cached(root, CONTENT)
    src = make_source(DIGEST)
    result = fetch_file(src, src.files[0], pin=False)
    assert result.status == "cached"
    assert verify_cached(src, "a.txt").read_bytes() == CONTENT


def test_tampered_cached_file_fails_fetch_and_build(root: Path) -> None:
    put_cached(root, CONTENT + b"x")
    src = make_source(DIGEST)
    with pytest.raises(PipelineError, match="sha256 mismatch"):
        fetch_file(src, src.files[0], pin=False)
    with pytest.raises(PipelineError, match="sha256 mismatch"):
        verify_cached(src, "a.txt")


def test_unpinned_file_is_refused_without_pin_mode(root: Path) -> None:
    put_cached(root, CONTENT)
    src = make_source("")
    with pytest.raises(PipelineError, match="no sha256"):
        fetch_file(src, src.files[0], pin=False)
    result = fetch_file(src, src.files[0], pin=True)
    assert (result.status, result.sha256) == ("unpinned", DIGEST)
    with pytest.raises(PipelineError, match="not pinned"):
        verify_cached(src, "a.txt")


def test_missing_cache_file_fails_build(root: Path) -> None:
    with pytest.raises(PipelineError, match="not in the cache"):
        verify_cached(make_source(DIGEST), "a.txt")


def test_load_source_reports_missing_keys(tmp_path: Path) -> None:
    path = tmp_path / "source.toml"
    path.write_text('[source]\nid = "x"\n', encoding="utf-8")
    with pytest.raises(PipelineError, match="missing required key 'name'"):
        load_source(path)


def mirrored_source() -> Source:
    src = make_source(DIGEST)
    f = src.files[0]
    mirrored = SourceFile(f.name, "https://upstream.invalid/a", f.version, f.sha256, mirror="m")
    return Source(**{**src.__dict__, "files": (mirrored,)})


def fake_download(responses: dict[str, bytes | None]) -> Callable[[str, Path], None]:
    def run(url: str, dest: Path) -> None:
        body = responses[url]
        if body is None:
            raise PipelineError(f"download failed: {url}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)

    return run


def test_mirror_is_preferred(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = mirrored_source()
    monkeypatch.setattr(fetch, "download", fake_download({"m": CONTENT}))
    assert fetch_file(src, src.files[0], pin=False).status == "downloaded"


@pytest.mark.parametrize("mirror_body", [None, b"changed"])
def test_upstream_is_used_when_mirror_fails(
    root: Path, monkeypatch: pytest.MonkeyPatch, mirror_body: bytes | None
) -> None:
    src = mirrored_source()
    responses = {"m": mirror_body, "https://upstream.invalid/a": CONTENT}
    monkeypatch.setattr(fetch, "download", fake_download(responses))
    assert fetch_file(src, src.files[0], pin=False).status == "downloaded"
    assert verify_cached(src, "a.txt").read_bytes() == CONTENT


def test_fetch_fails_when_no_url_matches_the_pin(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = mirrored_source()
    responses = {"m": None, "https://upstream.invalid/a": b"changed"}
    monkeypatch.setattr(fetch, "download", fake_download(responses))
    with pytest.raises(PipelineError, match="sha256 mismatch"):
        fetch_file(src, src.files[0], pin=False)
