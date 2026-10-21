"""Download pinned source files into ``.cache/`` and verify their sha256.

Rules (README "Sources"):
- Pinned files are downloaded from their ``mirror`` (exact pinned bytes kept in a
  siyak-data release) when one is set, else, or if the mirror fails, from the
  upstream ``url``. Either way the bytes must match the pin.
- ``manual = true`` marks a file whose upstream needs a form (e.g. an e-mail
  address). It is never downloaded from ``url``: a maintainer saves it into
  ``.cache/`` by hand, or ``fetch`` takes the exact pinned bytes from ``mirror``.
- A file without a pinned sha256 is never accepted. ``fetch --pin`` downloads
  it and prints the computed hash; a maintainer reviews the file and writes
  the hash into ``source.toml`` by hand.
- A cached file whose hash differs from the pin is an error, never silently
  replaced: delete it to download again.
- ``build`` re-checks every input with :func:`verify_cached` before reading it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import httpx

from pipeline.errors import PipelineError
from pipeline.sources import Source, SourceFile

USER_AGENT = "siyak-data (+https://github.com/siyak/siyak-data)"
TIMEOUT = httpx.Timeout(60.0, connect=20.0)


def sha256_file(path: Path) -> str:
    """Return the hex sha256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class FetchResult:
    """Outcome for one file."""

    source_id: str
    name: str
    path: Path
    sha256: str
    status: str  # "cached", "downloaded" or "unpinned"


def download(url: str, dest: Path) -> None:
    """Stream ``url`` to ``dest`` (via a ``.part`` file); raise ``PipelineError`` on failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        with (
            httpx.stream(
                "GET",
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
                follow_redirects=True,
            ) as response,
            part.open("wb") as out,
        ):
            response.raise_for_status()
            for chunk in response.iter_bytes():
                out.write(chunk)
    except httpx.HTTPError as exc:
        part.unlink(missing_ok=True)
        raise PipelineError(f"download failed: {url}: {exc}") from exc
    part.replace(dest)


def _mismatch(source: Source, f: SourceFile, path: Path, actual: str) -> PipelineError:
    return PipelineError(
        f"sha256 mismatch for {source.id}/{f.name}\n"
        f"  file:     {path}\n"
        f"  expected: {f.sha256}  (pinned in {source.path})\n"
        f"  actual:   {actual}\n"
        "  The upstream file or the cached copy has changed. Do not re-pin without "
        "reviewing the difference (docs/adding-a-source.md)."
    )


def fetch_file(source: Source, f: SourceFile, *, pin: bool) -> FetchResult:
    """Make sure one file is in the cache and matches its pin.

    With ``pin=True``, an unpinned file is downloaded and reported with
    status ``"unpinned"`` instead of failing.
    """
    path = source.cache_path(f.name)
    if not f.sha256 and not pin:
        raise PipelineError(
            f"{source.id}/{f.name} has no sha256 in {source.path}; "
            "run 'siyak-data fetch --pin' and review the file first"
        )
    if path.exists():
        actual = sha256_file(path)
        if f.sha256 and actual != f.sha256:
            raise _mismatch(source, f, path, actual)
        status = "cached" if f.sha256 else "unpinned"
        return FetchResult(source.id, f.name, path, actual, status)
    if f.manual and not (f.sha256 and f.mirror):
        raise PipelineError(
            f"{source.id}/{f.name} must be downloaded by hand (the source requires a form):\n"
            f"  1. download it from {f.url}\n"
            f"  2. save it unchanged as {path}\n"
            "  3. run this command again (the sha256 check still applies)"
        )
    if not f.sha256:
        download(f.url, path)
        return FetchResult(source.id, f.name, path, sha256_file(path), "unpinned")
    failures: list[str] = []
    urls = [f.mirror] if f.manual else [f.mirror, f.url]
    for url in [u for u in urls if u]:
        try:
            download(url, path)
        except PipelineError as exc:
            failures.append(str(exc))
            continue
        actual = sha256_file(path)
        if actual == f.sha256:
            return FetchResult(source.id, f.name, path, actual, "downloaded")
        rejected = path.with_name(path.name + ".rejected")
        path.replace(rejected)
        failures.append(str(_mismatch(source, f, rejected, actual)))
    raise PipelineError("\n".join(failures))


def fetch_sources(sources: list[Source], *, pin: bool = False) -> list[FetchResult]:
    """Fetch every file of the given sources."""
    return [fetch_file(s, f, pin=pin) for s in sources for f in s.files]


def verify_cached(source: Source, name: str) -> Path:
    """Return the cached path of a source file after checking its pinned sha256."""
    f = source.file(name)
    path = source.cache_path(name)
    if not f.sha256:
        raise PipelineError(f"{source.id}/{name} is not pinned in {source.path}")
    if not path.exists():
        raise PipelineError(f"{source.id}/{name} is not in the cache; run 'siyak-data fetch'")
    actual = sha256_file(path)
    if actual != f.sha256:
        raise _mismatch(source, f, path, actual)
    return path
