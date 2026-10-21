"""zstd compression of SQLite packs (docs/pack-format.md §4.3).

Every downloadable SQLite pack is published as ``<id>.sqlite.zst``: a single
zstd frame with the content size and a checksum in its header. core.db is not
compressed, because the app installer is compressed already.

Compression runs single-threaded at a fixed level, so the output is
deterministic for a given input and zstd version (reproducible builds).
Decompression mirrors the app: it refuses output larger than the expected size,
because a pack is untrusted input (spec §14.3).
"""

from __future__ import annotations

from pathlib import Path

import zstandard

from pipeline.errors import PipelineError

ZSTD_LEVEL = 19
SUFFIX = ".zst"
#: Upper bound for a decompressed pack when no expected size is known (manifest generation).
MAX_PACK_SIZE = 4 << 30
_CHUNK = 1 << 20
_FRAME_HEADER_MAX = 18


def compress_pack(src: Path) -> Path:
    """Write ``<src>.zst`` next to ``src`` and return its path."""
    out = src.with_name(src.name + SUFFIX)
    cctx = zstandard.ZstdCompressor(level=ZSTD_LEVEL, write_checksum=True, write_content_size=True)
    with src.open("rb") as ifh, out.open("wb") as ofh:
        cctx.copy_stream(ifh, ofh, size=src.stat().st_size)
    return out


def decompress_pack(src: Path, dest: Path, max_size: int) -> Path:
    """Decompress ``src`` to ``dest``; fail if the output would exceed ``max_size`` bytes."""
    with src.open("rb") as fh:
        header = fh.read(_FRAME_HEADER_MAX)
    try:
        params = zstandard.get_frame_parameters(header)
    except zstandard.ZstdError as exc:
        raise PipelineError(f"{src.name}: not a valid zstd file: {exc}") from exc
    if params.content_size != zstandard.CONTENTSIZE_UNKNOWN and params.content_size > max_size:
        raise PipelineError(
            f"{src.name}: frame declares {params.content_size} bytes, limit is {max_size}"
        )
    written = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            src.open("rb") as ifh,
            zstandard.ZstdDecompressor().stream_reader(ifh) as reader,
            dest.open("wb") as ofh,
        ):
            while chunk := reader.read(_CHUNK):
                written += len(chunk)
                if written > max_size:
                    raise PipelineError(f"{src.name}: decompressed size exceeds {max_size} bytes")
                ofh.write(chunk)
    except zstandard.ZstdError as exc:
        dest.unlink(missing_ok=True)
        raise PipelineError(f"{src.name}: not a valid zstd file: {exc}") from exc
    except PipelineError:
        dest.unlink(missing_ok=True)
        raise
    return dest
