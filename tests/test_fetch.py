import hashlib
import zipfile
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


def manual_source(sha: str, mirror: str = "") -> Source:
    src = make_source(sha)
    f = src.files[0]
    manual = SourceFile(
        f.name, "https://example.org/form", f.version, sha, mirror=mirror, manual=True
    )
    return Source(**{**src.__dict__, "files": (manual,)})


def test_manual_file_is_never_downloaded_from_url(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch, "download", fake_download({}))  # any call would KeyError
    src = manual_source(DIGEST)
    with pytest.raises(PipelineError, match="must be downloaded by hand"):
        fetch_file(src, src.files[0], pin=False)
    with pytest.raises(PipelineError, match="must be downloaded by hand"):
        fetch_file(manual_source(""), src.files[0], pin=True)


def test_manual_file_in_cache_is_checked(root: Path) -> None:
    put_cached(root, CONTENT)
    src = manual_source(DIGEST)
    assert fetch_file(src, src.files[0], pin=False).status == "cached"


def test_manual_file_comes_from_mirror_once_pinned(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch, "download", fake_download({"m": CONTENT}))
    src = manual_source(DIGEST, mirror="m")
    assert fetch_file(src, src.files[0], pin=False).status == "downloaded"


def test_member_is_extracted_from_a_pinned_zip(root: Path) -> None:
    zip_path = root / ".cache" / "demo" / "bundle.zip"
    zip_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.txt", CONTENT)
        zf.writestr("other.txt", b"not extracted")
    zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    src = make_source(DIGEST)
    files = (
        SourceFile("bundle.zip", "https://example.org/form", "1", zip_sha, manual=True),
        SourceFile("a.txt", "", "1", DIGEST, extract_from="bundle.zip"),
    )
    src = Source(**{**src.__dict__, "files": files})
    results = fetch.fetch_sources([src])
    assert [r.status for r in results] == ["cached", "cached"]
    assert verify_cached(src, "a.txt").read_bytes() == CONTENT
    assert not (root / ".cache" / "demo" / "other.txt").exists()
