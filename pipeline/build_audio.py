"""Recitation audio packs (``audio.<reciter>.tar.zst``, pack-format §4.10).

An audio pack holds ``audio.sqlite`` (``pack_info`` only), ``audio/LICENSE`` and one
mp3 per verse, ``audio/SSSAAA.mp3`` (6,236 files). The audio comes from Quran.com
(quran_com.py) and is re-encoded to mono MP3 at 64 kbit/s, so a reciter fits in a
single release asset below GitHub's 2 GiB limit.

The upstream files are many (6,236 per verse recitation), so they are not pinned one
by one in ``source.toml`` but in ``sources/audio/<id>/files.tsv`` (``name``,
``sha256``, ``url``); chapter recitations also keep ``timings.tsv`` (``surah``,
``ayah``, ``start_ms``, ``end_ms``) from the Quran.com API. ``fetch-audio --pin``
writes both after downloading; afterwards every build checks every file against them.

Audio packs are too large to rebuild in the data release workflow. A maintainer
builds them locally, uploads them to an ``audio-*`` release and pins each asset in
``[build.prebuilt]`` (``pin-audio``); the manifest lists the pinned asset
(manifest.py) without downloading it.

``[build]`` keys:
- ``quran_com = "verses"`` with ``recitation_id`` (API v4),
  ``quran_com = "chapters"`` with ``reciter_id`` (QDC), or
  ``everyayah = "<directory>"`` for a recitation that Quran.com has only as chapter
  files whose verse timings do not fit them; EveryAyah has the same recitation as
  verse files, so nothing is cut;
- ``prebuilt = { tag, size, installed_size, sha256 }`` once uploaded.
"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx

from pipeline import quran_com
from pipeline.archive import build_archive, extract_archive
from pipeline.build_translation import require_pack
from pipeline.compress import AUDIO_ZSTD_LEVEL, frame_content_size
from pipeline.errors import PipelineError
from pipeline.fetch import TIMEOUT, USER_AGENT, sha256_file
from pipeline.install import (
    AUDIO_DB_MEMBER,
    AUDIO_LICENSE_MEMBER,
    AYAH_COUNTS,
    audio_member,
    audio_members,
)
from pipeline.paths import cache_dir
from pipeline.schema import SCHEMA_VERSION, PackInfo, finalize, new_database, write_pack_info
from pipeline.sources import Source

FILES_TSV = "files.tsv"
TIMINGS_TSV = "timings.tsv"
BITRATE = "64k"
#: GitHub refuses release assets of 2 GiB or more.
MAX_ASSET_SIZE = 2 << 30
#: Verse files shorter than this are not a recitation (a broken cut or file).
MIN_VERSE_SECONDS = 0.3
#: Where a chapter recitation's first verse starts, before its timing (ms).
LEAD_IN_MS = 150
AUDIO_RELEASE_PREFIX = "audio-"


@dataclass(frozen=True)
class Pin:
    """One pinned upstream file."""

    name: str
    sha256: str
    url: str


def verses() -> list[tuple[int, int]]:
    """Every (surah, ayah) in Mushaf order."""
    return [
        (surah, ayah)
        for surah, count in enumerate(AYAH_COUNTS, start=1)
        for ayah in range(1, count + 1)
    ]


def _everyayah_dir(source: Source) -> str | None:
    value = source.extra.get("everyayah")
    if value is None:
        return None
    if not isinstance(value, str) or "quran_com" in source.extra:
        raise PipelineError(
            f"{source.path}: [build] everyayah must be a directory name, without quran_com"
        )
    return value


def mode(source: Source) -> str:
    """``verses`` or ``chapters`` (``[build] quran_com``; ``everyayah`` is ``verses``)."""
    if _everyayah_dir(source) is not None:
        return "verses"
    value = source.extra.get("quran_com")
    if value not in ("verses", "chapters"):
        raise PipelineError(f"{source.path}: [build] quran_com must be 'verses' or 'chapters'")
    return str(value)


def _api_id(source: Source) -> int:
    key = "recitation_id" if mode(source) == "verses" else "reciter_id"
    value = source.extra.get(key)
    if not isinstance(value, int):
        raise PipelineError(f"{source.path}: [build] {key} must be an integer")
    return value


def upstream_dir(source: Source) -> Path:
    """Cache directory of the upstream mp3 files."""
    return cache_dir() / source.id / "upstream"


def _scratch_dir() -> Path:
    """Where encoding and checking unpack gigabytes: the cache, not a small /tmp.

    Created on demand, since a fresh checkout (CI) has no ``.cache/``.
    """
    path = cache_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _source_dir(source: Source) -> Path:
    return source.path.parent


# --- pins -----------------------------------------------------------------------------


def read_pins(source: Source) -> list[Pin]:
    """The pinned upstream files of a source (``files.tsv``)."""
    path = _source_dir(source) / FILES_TSV
    if not path.exists():
        raise PipelineError(f"{path} is missing; run 'siyak-data fetch-audio --pin'")
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    pins = [Pin(r["name"], r["sha256"], r["url"]) for r in rows]
    if len({p.name for p in pins}) != len(pins):
        raise PipelineError(f"{path}: duplicate names")
    return pins


def write_pins(source: Source, pins: Iterable[Pin]) -> Path:
    """Write ``files.tsv`` sorted by name."""
    path = _source_dir(source) / FILES_TSV
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(["name", "sha256", "url"])
        for pin in sorted(pins, key=lambda p: p.name):
            writer.writerow([pin.name, pin.sha256, pin.url])
    return path


def read_timings(source: Source) -> dict[tuple[int, int], tuple[int, int]]:
    """Verse start and end (ms) in the chapter files of a chapter recitation."""
    path = _source_dir(source) / TIMINGS_TSV
    if not path.exists():
        raise PipelineError(f"{path} is missing; run 'siyak-data fetch-audio --pin'")
    with path.open(encoding="utf-8", newline="") as fh:
        return {
            (int(r["surah"]), int(r["ayah"])): (int(r["start_ms"]), int(r["end_ms"]))
            for r in csv.DictReader(fh, delimiter="\t")
        }


def write_timings(source: Source, timings: Iterable[quran_com.VerseTiming]) -> Path:
    """Write ``timings.tsv`` in Mushaf order."""
    path = _source_dir(source) / TIMINGS_TSV
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(["surah", "ayah", "start_ms", "end_ms"])
        for t in sorted(timings, key=lambda t: (t.surah, t.ayah)):
            writer.writerow([t.surah, t.ayah, t.start_ms, t.end_ms])
    return path


def check_timings(timings: dict[tuple[int, int], tuple[int, int]], where: str) -> None:
    """Every verse once, each with a start before its end, starting after the one before.

    Quran.com's timings may overlap by a few milliseconds; the cut then falls at the
    later verse's start (:func:`chapter_cuts`).
    """
    missing = [v for v in verses() if v not in timings]
    extra = sorted(set(timings) - set(verses()))
    if missing or extra:
        raise PipelineError(f"{where}: timings miss {missing[:5]}… or have extra {extra[:5]}…")
    for surah, count in enumerate(AYAH_COUNTS, start=1):
        previous_start = -1
        for ayah in range(1, count + 1):
            start, end = timings[(surah, ayah)]
            if not previous_start < start < end:
                raise PipelineError(
                    f"{where}: verse {surah}:{ayah} timing {start}-{end} is out of order"
                )
            previous_start = start


# --- fetch ----------------------------------------------------------------------------


def _download_one(client: httpx.Client, url: str, dest: Path, attempts: int = 6) -> None:
    """Download one file, retrying with a growing pause (a long download meets network
    blips, e.g. a failed DNS lookup)."""
    part = dest.with_name(dest.name + ".part")
    last: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(min(60, 2**attempt))
        try:
            with client.stream("GET", url) as response, part.open("wb") as out:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    out.write(chunk)
            part.replace(dest)
            return
        except httpx.HTTPError as exc:
            last = exc
            part.unlink(missing_ok=True)
    raise PipelineError(f"download failed: {url}: {last}")


def _upstream_list(source: Source) -> list[tuple[str, str]]:
    """``(name, url)`` of every upstream file, from the Quran.com API or EveryAyah."""
    directory = _everyayah_dir(source)
    if directory is not None:
        return [
            (f"{s:03d}{a:03d}.mp3", quran_com.everyayah_url(directory, s, a)) for s, a in verses()
        ]
    if mode(source) == "verses":
        files = quran_com.verse_files(_api_id(source))
        missing = [v for v in verses() if v not in files]
        if missing:
            raise PipelineError(f"{source.id}: Quran.com lists no file for {missing[:5]}…")
        return [(f"{s:03d}{a:03d}.mp3", files[(s, a)]) for s, a in verses()]
    chapters = quran_com.chapter_files(_api_id(source))
    timings = {(t.surah, t.ayah): (t.start_ms, t.end_ms) for c in chapters for t in c.timings}
    check_timings(timings, source.id)
    write_timings(source, (t for c in chapters for t in c.timings))
    return [(f"{c.surah:03d}.mp3", c.url) for c in chapters]


def fetch_audio(
    source: Source,
    *,
    pin: bool,
    workers: int = 8,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Download the upstream files of an audio source into the cache and check them.

    With ``pin``, a source without ``files.tsv`` is listed through the Quran.com API,
    downloaded and pinned (``files.tsv``, and ``timings.tsv`` for chapters); review
    the result before committing it. Returns the cache directory.
    """
    pins_path = _source_dir(source) / FILES_TSV
    if pins_path.exists():
        wanted = [(p.name, p.url) for p in read_pins(source)]
        expected = {p.name: p.sha256 for p in read_pins(source)}
    elif pin:
        wanted = _upstream_list(source)
        expected = {}
    else:
        raise PipelineError(f"{pins_path} is missing; run 'siyak-data fetch-audio --pin'")
    dest = upstream_dir(source)
    dest.mkdir(parents=True, exist_ok=True)
    todo = [(name, url) for name, url in wanted if not (dest / name).exists()]
    done = len(wanted) - len(todo)
    with (
        httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True
        ) as client,
        ThreadPoolExecutor(max_workers=workers) as pool,
    ):
        futures = [pool.submit(_download_one, client, url, dest / name) for name, url in todo]
        for future in futures:
            future.result()
            done += 1
            if progress:
                progress(done, len(wanted))
    if expected:
        verify_upstream(source)
    else:
        write_pins(source, (Pin(n, sha256_file(dest / n), u) for n, u in wanted))
    return dest


def verify_upstream(source: Source) -> list[Path]:
    """Check every cached upstream file against ``files.tsv``; return them in order."""
    dest = upstream_dir(source)
    paths = []
    for p in read_pins(source):
        path = dest / p.name
        if not path.exists():
            raise PipelineError(f"{source.id}/{p.name} is not in the cache; run 'fetch-audio'")
        actual = sha256_file(path)
        if actual != p.sha256:
            raise PipelineError(
                f"sha256 mismatch for {source.id}/{p.name}: expected {p.sha256}, got {actual}. "
                "Delete the file to download it again; do not re-pin without review."
            )
        paths.append(path)
    return paths


# --- encode ---------------------------------------------------------------------------

_ENCODE = ["-map", "0:a:0", "-ac", "1", "-c:a", "libmp3lame", "-b:a", BITRATE]
_BITEXACT = ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact"]


def _ffmpeg(args: list[str]) -> None:
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise PipelineError("ffmpeg is not installed (brew install ffmpeg)") from exc
    except subprocess.CalledProcessError as exc:
        raise PipelineError(f"ffmpeg failed: {' '.join(command)}\n{exc.stderr}") from exc


def ffmpeg_version() -> str:
    """First line of ``ffmpeg -version`` (recorded in ``pack_info.source_version``)."""
    try:
        out = subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise PipelineError("ffmpeg is not installed (brew install ffmpeg)") from exc
    words = out.stdout.split()
    return words[2] if len(words) > 2 else "unknown"


def encode_verse(src: Path, dest: Path) -> None:
    """Re-encode one verse file to mono MP3 at 64 kbit/s, without tags."""
    _ffmpeg(["-i", str(src), *_ENCODE, *_BITEXACT, str(dest)])


def chapter_cuts(timings: list[tuple[int, int]]) -> list[int]:
    """Where each verse of a chapter file starts (ms).

    A verse starts in the middle of the pause before it (the first one shortly
    before its timing) and ends where the next one starts; the last runs to the end
    of the file, so no recited sound is cut off.
    """
    cuts = [max(0, timings[0][0] - LEAD_IN_MS)]
    for (_, previous_end), (start, _) in pairwise(timings):
        cuts.append((previous_end + start) // 2 if previous_end < start else start)
    return cuts


def encode_chapter(src: Path, cuts_ms: list[int], out_dir: Path) -> list[Path]:
    """Cut a chapter file into one encoded file per verse (in one ffmpeg pass)."""
    duration = float(probe(src).get("duration", 0))
    if cuts_ms and cuts_ms[-1] / 1000 + MIN_VERSE_SECONDS > duration:
        raise PipelineError(
            f"{src.name} is {duration:.1f} s long, but its last verse starts at "
            f"{cuts_ms[-1] / 1000:.1f} s: the file is not the recording the timings are for"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    times = ",".join(f"{ms / 1000:.3f}" for ms in cuts_ms)
    _ffmpeg(
        [
            "-i", str(src), *_ENCODE, *_BITEXACT,
            "-f", "segment", "-segment_times", times, "-reset_timestamps", "1",
            str(out_dir / "%04d.mp3"),
        ]
    )  # fmt: skip
    # Segment 0 is the part before the first verse (silence, isti'adha or basmala).
    parts = [out_dir / f"{i:04d}.mp3" for i in range(1, len(cuts_ms) + 1)]
    missing = [p.name for p in parts if not p.exists()]
    if missing:
        raise PipelineError(f"{src.name}: ffmpeg wrote no segment {missing[:3]}")
    return parts


def encode_all(source: Source, work: Path, workers: int) -> dict[str, Path]:
    """Encode every verse into ``work``; return archive member name → file."""
    verse_list = verses()
    upstream = upstream_dir(source)
    out: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        if mode(source) == "verses":
            jobs = []
            for surah, ayah in verse_list:
                name = f"{surah:03d}{ayah:03d}.mp3"
                dest = work / name
                out[audio_member(surah, ayah)] = dest
                jobs.append(pool.submit(encode_verse, upstream / name, dest))
            for job in jobs:
                job.result()
            return out
        timings = read_timings(source)
        check_timings(timings, str(_source_dir(source) / TIMINGS_TSV))
        chapter_jobs: list[tuple[int, Future[list[Path]]]] = []
        for surah, count in enumerate(AYAH_COUNTS, start=1):
            spans = [timings[(surah, ayah)] for ayah in range(1, count + 1)]
            chapter_jobs.append(
                (
                    surah,
                    pool.submit(
                        encode_chapter,
                        upstream / f"{surah:03d}.mp3",
                        chapter_cuts(spans),
                        work / f"{surah:03d}",
                    ),
                )
            )
        for surah, chapter_job in chapter_jobs:
            for ayah, path in enumerate(chapter_job.result(), start=1):
                out[audio_member(surah, ayah)] = path
    return out


# --- pack -----------------------------------------------------------------------------


def source_version(source: Source) -> str:
    """``pack_info.source_version``: the upstream list, its pins and the encoder."""
    pins = sha256_file(_source_dir(source) / FILES_TSV)[:16]
    directory = _everyayah_dir(source)
    upstream = (
        f"everyayah {directory}"
        if directory is not None
        else f"quran.com {mode(source)} {_api_id(source)}"
    )
    return f"{upstream}; files.tsv@{pins}; ffmpeg {ffmpeg_version()}"


def build_audio_pack(
    source: Source, out_dir: Path, *, built_at: str, mtime: int, workers: int | None = None
) -> list[Path]:
    """Build ``<id>.sqlite`` (pack_info only) and ``<id>.tar.zst``; return both paths."""
    pack = require_pack(source)
    if pack.type != "audio":
        raise PipelineError(f"{source.path}: pack type is '{pack.type}', not 'audio'")
    license_file = _source_dir(source) / "LICENSE"
    if not license_file.exists():
        raise PipelineError(f"{license_file} is missing (shipped as {AUDIO_LICENSE_MEMBER})")
    verify_upstream(source)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="siyak-audio-", dir=_scratch_dir()) as tmp:
        work = Path(tmp)
        encoded = encode_all(source, work, workers or os.cpu_count() or 4)
        db = out_dir / f"{pack.id}.sqlite"
        info = PackInfo(
            pack.id, pack.type, pack.version, SCHEMA_VERSION, built_at, source_version(source)
        )
        with closing(new_database(db)) as conn:
            write_pack_info(conn, info)
            conn.commit()
            finalize(conn)
        members = [(AUDIO_DB_MEMBER, db), (AUDIO_LICENSE_MEMBER, license_file)]
        members += [(name, encoded[name]) for name in sorted(encoded)]
        if {m for m, _ in members} != audio_members():
            raise PipelineError(f"{pack.id}: encoded files do not cover every verse")
        archive = build_archive(out_dir, pack.id, members, mtime, AUDIO_ZSTD_LEVEL)
    return [db, archive]


def drop_upstream(source: Source) -> None:
    """Delete the cached upstream files of a source (they are pinned and can be fetched again)."""
    shutil.rmtree(upstream_dir(source), ignore_errors=True)


# --- validation -----------------------------------------------------------------------


def probe(path: Path) -> dict[str, Any]:
    """Codec, channels, bit rate and duration of an audio file (ffprobe)."""
    command = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,channels:format=duration,bit_rate",
        "-of", "default=noprint_wrappers=1", str(path),
    ]  # fmt: skip
    try:
        out = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    except FileNotFoundError as exc:
        raise PipelineError("ffprobe is not installed (brew install ffmpeg)") from exc
    except subprocess.CalledProcessError as exc:
        raise PipelineError(f"{path.name}: ffprobe cannot read it: {exc.stderr.strip()}") from exc
    values = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return values


def check_audio_file(path: Path) -> str | None:
    """Why a verse file is not a usable recitation, or None."""
    try:
        info = probe(path)
    except PipelineError as exc:
        return str(exc)
    if info.get("codec_name") != "mp3" or info.get("channels") != "1":
        return f"{path.name}: {info.get('codec_name')} with {info.get('channels')} channels"
    try:
        duration = float(info.get("duration", "0"))
    except ValueError:
        duration = 0.0
    if duration < MIN_VERSE_SECONDS:
        return f"{path.name}: {duration:.2f} s is too short"
    return None


def check_audio_pack(archive: Path, pack_id: str, version: str, workers: int = 8) -> list[str]:
    """Validation gate of a built audio pack; return the problems found."""
    problems: list[str] = []
    if archive.stat().st_size >= MAX_ASSET_SIZE:
        problems.append(f"{archive.name}: {archive.stat().st_size:,} bytes, GitHub allows < 2 GiB")
    with tempfile.TemporaryDirectory(prefix="siyak-audio-check-", dir=_scratch_dir()) as tmp:
        files = extract_archive(
            archive,
            Path(tmp),
            expected=set(audio_members()),
            max_size=frame_content_size(archive),
        )
        import sqlite3  # noqa: PLC0415

        from pipeline.schema import read_pack_info  # noqa: PLC0415

        with closing(sqlite3.connect(files[AUDIO_DB_MEMBER])) as conn:
            info = read_pack_info(conn)
        if (info.id, info.type, info.version) != (pack_id, "audio", version):
            problems.append(f"pack_info is {info.id}/{info.type} {info.version}")
        if not files[AUDIO_LICENSE_MEMBER].read_text(encoding="utf-8").strip():
            problems.append(f"{AUDIO_LICENSE_MEMBER} is empty")
        mp3s = [files[audio_member(s, a)] for s, a in verses()]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            problems += [p for p in pool.map(check_audio_file, mp3s) if p]
    return problems


# --- prebuilt -------------------------------------------------------------------------


def prebuilt(source: Source) -> dict[str, Any] | None:
    """The pinned release asset of an audio pack (``[build.prebuilt]``), if any."""
    value = source.extra.get("prebuilt")
    if value is None:
        return None
    keys = {"tag", "size", "installed_size", "sha256"}
    if not isinstance(value, dict) or set(value) != keys:
        raise PipelineError(f"{source.path}: [build.prebuilt] needs exactly {sorted(keys)}")
    if not str(value["tag"]).startswith(AUDIO_RELEASE_PREFIX):
        raise PipelineError(f"{source.path}: prebuilt tag must start with '{AUDIO_RELEASE_PREFIX}'")
    return dict(value)


def prebuilt_block(archive: Path, tag: str) -> str:
    """The ``[build.prebuilt]`` table to paste into source.toml for an uploaded pack."""
    return (
        "[build.prebuilt]\n"
        f'tag = "{tag}"\n'
        f"size = {archive.stat().st_size}\n"
        f"installed_size = {frame_content_size(archive)}\n"
        f'sha256 = "{sha256_file(archive)}"\n'
    )
