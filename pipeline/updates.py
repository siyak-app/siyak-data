"""``check-updates``: compare upstream sources with their pinned versions.

Pinned files are fetched from mirrors, so an upstream change never breaks a
build; this command is how such changes are noticed. It downloads every pinned
file from its upstream ``url`` into a temporary directory and reports, per
file, whether it is unchanged or which lines differ. Nothing is written to
``.cache/`` or ``sources/``; re-pinning stays a reviewed, manual step.

Tanzil's copyright line contains the current year, so a yearly change of that
single line is expected and reported as such.

Quranpedia tafsir dumps (sources with ``[build] quranpedia_book``) are large
and rebuilt in place, so they are not downloaded: the command compares the
pin with the sha256 in the dump manifest and asks the changes API
(``/api/v1/changes?since=<pinned dump version>``) for corrections to the book.
"""

from __future__ import annotations

import difflib
import functools
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.errors import PipelineError
from pipeline.fetch import download, sha256_file
from pipeline.sources import Source

MAX_SHOWN_LINES = 10


@dataclass(frozen=True)
class UpdateReport:
    """Comparison of one upstream file with its pin."""

    source_id: str
    name: str
    status: str  # "unchanged", "changed" or "error"
    detail: list[str]


def _changed_lines(old: Path, new: Path) -> list[str]:
    try:
        a = old.read_text(encoding="utf-8").splitlines()
        b = new.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return ["(binary file differs)"]
    return [
        line
        for line in difflib.unified_diff(a, b, lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


QURANPEDIA_MANIFEST = "https://quranpedia.net/dumps/manifest.json"
QURANPEDIA_CHANGES = "https://quranpedia.net/api/v1/changes?since={since}"


@functools.cache
def _json(url: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="siyak-updates-") as tmp:
        path = Path(tmp) / "data.json"
        download(url, path)
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PipelineError(f"{url}: expected a JSON object")
    return data


def check_quranpedia(source: Source) -> list[UpdateReport]:
    """Compare a pinned dump with the dump manifest and the changes API."""
    book = int(source.extra["quranpedia_book"])
    reports = []
    for f in source.files:
        detail: list[str] = []
        try:
            files = _json(QURANPEDIA_MANIFEST).get("files", [])
            listed = {e["name"]: e for e in files if isinstance(e, dict)}
            entry = listed.get(f.name)
            if entry is None:
                detail.append("not in the dump manifest any more")
            elif entry.get("sha256") != f.sha256:
                detail.append(f"dump manifest has a new file (built {entry.get('built_at')})")
            changes = _json(QURANPEDIA_CHANGES.format(since=f.version)).get("changes", {})
            for kind in ("ayah_book_contents", "books"):
                table = changes.get(kind, {})
                rows = [r for r in table.get("rows", []) if int(r.get("book", -1)) == book]
                if rows:
                    where = ", ".join(f"{r.get('surah', '')}:{r.get('ayah', '')}" for r in rows[:5])
                    detail.append(
                        f"changes API: {len(rows)} {kind} change(s) since {f.version} {where}"
                    )
                if table.get("truncated"):
                    detail.append(f"changes API: the {kind} list is truncated; query a later date")
        except (PipelineError, KeyError, ValueError, AttributeError) as exc:
            reports.append(UpdateReport(source.id, f.name, "error", [str(exc)]))
            continue
        reports.append(
            UpdateReport(source.id, f.name, "changed" if detail else "unchanged", detail)
        )
    return reports


def check_source(source: Source) -> list[UpdateReport]:
    """Compare every pinned file of ``source`` with its upstream URL."""
    if "quranpedia_book" in source.extra:
        return check_quranpedia(source)
    reports: list[UpdateReport] = []
    with tempfile.TemporaryDirectory(prefix="siyak-updates-") as tmp:
        for f in source.files:
            if not f.sha256:
                continue
            upstream = Path(tmp) / f.name
            try:
                download(f.url, upstream)
            except PipelineError as exc:
                reports.append(UpdateReport(source.id, f.name, "error", [str(exc)]))
                continue
            if sha256_file(upstream) == f.sha256:
                reports.append(UpdateReport(source.id, f.name, "unchanged", []))
                continue
            pinned = source.cache_path(f.name)
            if pinned.exists() and sha256_file(pinned) == f.sha256:
                lines = _changed_lines(pinned, upstream)
                detail = [f"{len(lines)} changed line(s):", *lines[:MAX_SHOWN_LINES]]
            else:
                detail = ["upstream differs from the pin; run 'fetch' to compare line by line"]
            reports.append(UpdateReport(source.id, f.name, "changed", detail))
    return reports
