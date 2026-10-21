"""``check-updates``: compare upstream sources with their pinned versions.

Pinned files are fetched from mirrors, so an upstream change never breaks a
build; this command is how such changes are noticed. It downloads every pinned
file from its upstream ``url`` into a temporary directory and reports, per
file, whether it is unchanged or which lines differ. Nothing is written to
``.cache/`` or ``sources/``; re-pinning stays a reviewed, manual step.

Tanzil's copyright line contains the current year, so a yearly change of that
single line is expected and reported as such.
(Quranpedia tafsir dumps are added to this command in M1c.)
"""

from __future__ import annotations

import difflib
import tempfile
from dataclasses import dataclass
from pathlib import Path

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


def check_source(source: Source) -> list[UpdateReport]:
    """Compare every pinned file of ``source`` with its upstream URL."""
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
