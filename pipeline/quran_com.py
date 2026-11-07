"""Recitation audio from Quran.com (Quran.Foundation), for audio packs (pack-format §4.10).

Quran.com publishes two kinds of recitations:

- **verse recitations** (API v4 ``/recitations/{id}/by_chapter/{n}``): one mp3 per
  verse, served from ``verses.quran.com`` or the EveryAyah mirror on
  ``mirrors.quranicaudio.com``. A verse file never starts with the basmala.
- **chapter recitations** (QDC ``/audio/reciters/{id}/audio_files``): one mp3 per
  surah plus the start and end of every verse in it (``verse_timings``, ms). The
  pipeline cuts these into verse files.

Only the list of files and timings comes from the APIs; the audio itself is
pinned by sha256 in ``sources/audio/<id>/files.tsv`` (build_audio.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from pipeline.errors import PipelineError
from pipeline.fetch import TIMEOUT, USER_AGENT

V4_API = "https://api.quran.com/api/v4"
QDC_API = "https://api.qurancdn.com/api/qdc"
VERSES_HOST = "https://verses.quran.com/"
SURAH_COUNT = 114


@dataclass(frozen=True)
class VerseTiming:
    """Where a verse lies in a chapter file, in milliseconds."""

    surah: int
    ayah: int
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class ChapterAudio:
    """One surah of a chapter recitation."""

    surah: int
    url: str
    timings: tuple[VerseTiming, ...]


def absolute_url(url: str) -> str:
    """Turn the API's relative (``Alafasy/mp3/001001.mp3``) or scheme-less
    (``//mirrors.quranicaudio.com/…``) addresses into ``https://`` URLs."""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith(("https://", "http://")):
        return "https://" + url.removeprefix("https://").removeprefix("http://")
    return VERSES_HOST + url.lstrip("/")


def verse_key(key: str) -> tuple[int, int]:
    """``"2:255"`` → ``(2, 255)``."""
    surah, _, ayah = key.partition(":")
    try:
        return int(surah), int(ayah)
    except ValueError as exc:
        raise PipelineError(f"bad verse key {key!r} from Quran.com") from exc


def _get(client: httpx.Client, url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PipelineError(f"Quran.com API request failed: {url}: {exc}") from exc
    return data


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)


def verse_files(recitation_id: int) -> dict[tuple[int, int], str]:
    """Every verse's file URL of a verse recitation, keyed by (surah, ayah)."""
    files: dict[tuple[int, int], str] = {}
    with _client() as client:
        for surah in range(1, SURAH_COUNT + 1):
            page: int | None = 1
            while page is not None:
                data = _get(
                    client,
                    f"{V4_API}/recitations/{recitation_id}/by_chapter/{surah}",
                    {"per_page": 50, "page": page},
                )
                for item in data.get("audio_files", []):
                    files[verse_key(str(item["verse_key"]))] = absolute_url(str(item["url"]))
                next_page = data.get("pagination", {}).get("next_page")
                page = int(next_page) if next_page else None
    return files


def chapter_files(reciter_id: int) -> list[ChapterAudio]:
    """Every surah file and its verse timings of a chapter recitation."""
    chapters: list[ChapterAudio] = []
    with _client() as client:
        for surah in range(1, SURAH_COUNT + 1):
            data = _get(
                client,
                f"{QDC_API}/audio/reciters/{reciter_id}/audio_files",
                {"chapter": surah, "segments": "true"},
            )
            items = data.get("audio_files", [])
            if len(items) != 1:
                raise PipelineError(
                    f"reciter {reciter_id}, surah {surah}: expected one file, got {len(items)}"
                )
            item = items[0]
            timings = tuple(
                VerseTiming(
                    *verse_key(str(t["verse_key"])),
                    start_ms=int(t["timestamp_from"]),
                    end_ms=int(t["timestamp_to"]),
                )
                for t in item.get("verse_timings", [])
            )
            chapters.append(ChapterAudio(surah, absolute_url(str(item["audio_url"])), timings))
    return chapters
