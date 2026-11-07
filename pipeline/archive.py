"""Archive packs (``<id>.tar.zst``, docs/pack-format.md §4.4).

An archive pack is a tar file holding one SQLite database plus extra files
(for QAC: the original corpus file, its NOTICE and the license text),
compressed with the same zstd settings as SQLite packs.

The tar is deterministic: members in the given order, USTAR format, fixed
mtime (the build time), uid/gid 0, no user/group names, mode 0644. Extraction
mirrors the app: only regular files with exactly the expected relative names
are accepted, and the decompressed size is capped.
"""

from __future__ import annotations

import tarfile
from pathlib import Path, PurePosixPath

from pipeline.compress import ZSTD_LEVEL, compress_pack, decompress_pack
from pipeline.errors import PipelineError

TAR_SUFFIX = ".tar"


def build_archive(
    out_dir: Path,
    pack_id: str,
    members: list[tuple[str, Path]],
    mtime: int,
    level: int = ZSTD_LEVEL,
) -> Path:
    """Write ``<out_dir>/<pack_id>.tar.zst`` from ``(name in archive, file)`` pairs."""
    tar_path = out_dir / f"{pack_id}{TAR_SUFFIX}"
    with tarfile.open(tar_path, "w", format=tarfile.USTAR_FORMAT) as tar:
        for name, path in members:
            _check_name(name)
            info = tarfile.TarInfo(name)
            info.size = path.stat().st_size
            info.mtime = mtime
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as fh:
                tar.addfile(info, fh)
    compressed = compress_pack(tar_path, level)
    tar_path.unlink()
    return compressed


def _check_name(name: str) -> None:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or name != path.as_posix():
        raise PipelineError(f"archive member name {name!r} is not a plain relative path")


def extract_archive(src: Path, dest: Path, *, expected: set[str], max_size: int) -> dict[str, Path]:
    """Decompress and unpack ``src`` into ``dest``; return the path of every member.

    Fails unless the archive holds exactly the ``expected`` names, each once,
    all regular files.
    """
    dest.mkdir(parents=True, exist_ok=True)
    tar_path = decompress_pack(src, dest / "pack.tar", max_size)
    files = dest / "files"
    try:
        with tarfile.open(tar_path, "r:") as tar:
            members = tar.getmembers()
            names = [m.name for m in members]
            for member in members:
                _check_name(member.name)
                if not member.isreg():
                    raise PipelineError(f"{src.name}: member {member.name!r} is not a regular file")
            if sorted(names) != sorted(expected) or len(set(names)) != len(names):
                raise PipelineError(
                    f"{src.name}: members {sorted(names)}, expected {sorted(expected)}"
                )
            tar.extractall(files, filter="data")
    except tarfile.TarError as exc:
        raise PipelineError(f"{src.name}: not a valid tar archive: {exc}") from exc
    finally:
        tar_path.unlink(missing_ok=True)
    return {name: files / name for name in expected}
