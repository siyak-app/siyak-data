import tarfile
from pathlib import Path

import pytest

from pipeline.archive import build_archive, extract_archive
from pipeline.compress import compress_pack
from pipeline.errors import PipelineError

NAMES = {"pack.sqlite", "extra/NOTICE"}


@pytest.fixture
def members(tmp_path: Path) -> list[tuple[str, Path]]:
    (tmp_path / "a").write_bytes(b"database")
    (tmp_path / "b").write_bytes(b"notice text\n")
    return [("pack.sqlite", tmp_path / "a"), ("extra/NOTICE", tmp_path / "b")]


def test_round_trip_and_determinism(tmp_path: Path, members: list[tuple[str, Path]]) -> None:
    first = build_archive(tmp_path, "x", members, mtime=1792540800)
    assert first.name == "x.tar.zst"
    data = first.read_bytes()
    assert build_archive(tmp_path, "x", members, mtime=1792540800).read_bytes() == data
    files = extract_archive(first, tmp_path / "out", expected=NAMES, max_size=1 << 20)
    assert files["extra/NOTICE"].read_bytes() == b"notice text\n"
    assert not (tmp_path / "out" / "pack.tar").exists()


def test_unexpected_members_are_refused(tmp_path: Path, members: list[tuple[str, Path]]) -> None:
    archive = build_archive(tmp_path, "x", members, mtime=0)
    with pytest.raises(PipelineError, match="expected"):
        extract_archive(archive, tmp_path / "out", expected={"pack.sqlite"}, max_size=1 << 20)


@pytest.mark.parametrize("kind", ["symlink", "absolute", "parent"])
def test_unsafe_members_are_refused(tmp_path: Path, kind: str) -> None:
    payload = tmp_path / "one"
    payload.write_bytes(b"x")
    tar_path = tmp_path / "evil.tar"
    with tarfile.open(tar_path, "w", format=tarfile.USTAR_FORMAT) as tar:
        if kind == "symlink":
            info = tarfile.TarInfo("pack.sqlite")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
        else:
            info = tarfile.TarInfo("/pack.sqlite" if kind == "absolute" else "../pack.sqlite")
            info.size = 1
            with payload.open("rb") as fh:
                tar.addfile(info, fh)
    archive = compress_pack(tar_path)
    with pytest.raises(PipelineError):
        extract_archive(archive, tmp_path / "out", expected={"pack.sqlite"}, max_size=1 << 20)
    assert not (tmp_path / "out" / "files").exists() or not any(
        (tmp_path / "out" / "files").iterdir()
    )
