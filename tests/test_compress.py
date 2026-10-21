from pathlib import Path

import pytest
import zstandard

from pipeline.compress import compress_pack, decompress_pack
from pipeline.errors import PipelineError

DATA = b"SQLite format 3\x00" + bytes(range(256)) * 400


@pytest.fixture
def packed(tmp_path: Path) -> Path:
    src = tmp_path / "p.sqlite"
    src.write_bytes(DATA)
    return compress_pack(src)


def test_round_trip(packed: Path, tmp_path: Path) -> None:
    assert packed.name == "p.sqlite.zst"
    assert packed.stat().st_size < len(DATA)
    out = decompress_pack(packed, tmp_path / "out" / "p.sqlite", max_size=len(DATA))
    assert out.read_bytes() == DATA


def test_compression_is_deterministic(packed: Path) -> None:
    first = packed.read_bytes()
    assert compress_pack(packed.with_suffix("")).read_bytes() == first


def test_declared_size_over_limit_is_refused(packed: Path, tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="frame declares"):
        decompress_pack(packed, tmp_path / "x.sqlite", max_size=len(DATA) - 1)
    assert not (tmp_path / "x.sqlite").exists()


def test_invalid_file_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sqlite.zst"
    bad.write_bytes(b"not zstd at all, definitely not")
    with pytest.raises(PipelineError, match="not a valid zstd file"):
        decompress_pack(bad, tmp_path / "x.sqlite", max_size=1 << 20)


def test_streamed_size_over_limit_is_refused(tmp_path: Path) -> None:
    # A frame without a declared content size is still capped while streaming.
    blob = zstandard.ZstdCompressor(write_content_size=False).compress(DATA)
    src = tmp_path / "nosize.sqlite.zst"
    src.write_bytes(blob)
    with pytest.raises(PipelineError, match="decompressed size exceeds"):
        decompress_pack(src, tmp_path / "x.sqlite", max_size=len(DATA) // 2)
    assert not (tmp_path / "x.sqlite").exists()
