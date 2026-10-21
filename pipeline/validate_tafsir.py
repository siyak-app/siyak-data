"""Validation gates for tafsir packs (spec §5.2, §15.2; docs/pack-format.md §4.6).

- The published ``.sqlite.zst`` decompresses to the built database; its
  structure and ``pack_info`` are as expected; it installs into content.db.
- Passages: valid verse ids within one surah; commentary passages sorted and
  never overlapping; at most one ``introduction`` passage, passage 1 at 1:1;
  each has paragraphs numbered from 0, none empty.
- Paragraphs hold only the tafsir HTML subset; ``part`` is set exactly when
  ``page`` is, and pages are positive.
- **Text unchanged:** for every passage, the letters of its paragraphs equal
  the letters of the source sections it was built from, read from the pinned
  dump with an independent tag stripper. Together with the accounting check
  in ``pipeline/quranpedia.py`` (every source letter stored, repeated, or
  left out for a recorded reason) this proves no text was altered.
- Coverage is at least ``[build] min_coverage`` verses.
"""

from __future__ import annotations

import re
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.build_core import load_tanzil
from pipeline.build_tafsir import is_available, source_assembly
from pipeline.build_translation import require_pack, source_version, verse_ids
from pipeline.errors import PipelineError
from pipeline.gates import Report, install_into_core_copy, unpack_published
from pipeline.install import check_pack_structure
from pipeline.quranpedia import Key
from pipeline.schema import SCHEMA_VERSION, read_pack_info
from pipeline.sources import Source
from pipeline.tafsir_html import source_letters, subset_letters

_ALLOWED_TAG = re.compile(r'<(?:/?b|br|/span|span class="(?:ayah|ref|poem|hemistich)")>')
_ANY_TAG = re.compile(r"<[^>]*>")

Paragraph = tuple[int, str, str | None, int | None]


@dataclass
class _Pack:
    """What the gates read from one tafsir pack."""

    where: str
    source: Source
    passages: list[tuple[int, str, int, int, str]] = field(default_factory=list)
    paragraphs: dict[int, list[Paragraph]] = field(default_factory=dict)


@dataclass(frozen=True)
class _Context:
    profile: str
    core: Path
    ids: dict[Key, int]
    verse_text: dict[Key, str]


def check_tafsir_packs(
    dist: Path, sources: list[Source], tanzil: Source, core: Path, report: Report, *, profile: str
) -> None:
    """Run every tafsir gate on ``dist/<id>.sqlite.zst`` for each tafsir source."""
    if not sources:
        return
    inputs = load_tanzil(tanzil)
    ctx = _Context(
        profile,
        core,
        verse_ids(inputs.metadata),
        {(a.surah, a.ayah): a.text for a in inputs.clean.verses},
    )
    for source in sources:
        pack = require_pack(source)
        if not is_available(source):
            report.info.append(f"{pack.id}: optional source not ready (cache or pin), skipped")
            continue
        with tempfile.TemporaryDirectory(prefix="siyak-validate-") as tmp:
            published = unpack_published(dist / f"{pack.id}.sqlite", Path(tmp), report)
            if published is None:
                continue
            try:
                _check_pack(published, source, ctx, report)
            except PipelineError as exc:
                report.check(False, f"{pack.id}: {exc}")


def _check_pack(db: Path, source: Source, ctx: _Context, report: Report) -> None:
    pack = require_pack(source)
    data = _Pack(f"{pack.id}.sqlite", source)
    with closing(sqlite3.connect(db)) as conn:
        try:
            check_pack_structure(conn, pack.type)
            info = read_pack_info(conn)
        except (PipelineError, ValueError, sqlite3.Error) as exc:
            report.check(False, f"{data.where}: {exc}")
            return
        expected = (pack.id, pack.type, pack.version, SCHEMA_VERSION, source_version(source))
        actual = (info.id, info.type, info.version, info.schema_version, info.source_version)
        report.check(actual == expected, f"{data.where}: pack_info {actual} != {expected}")
        data.passages = conn.execute(
            "SELECT id, pack_id, verse_from, verse_to, kind FROM tafsir ORDER BY id"
        ).fetchall()
        for tid, idx, text, part, page in conn.execute(
            "SELECT tafsir_id, idx, text, part, page FROM tafsir_paragraphs ORDER BY tafsir_id, idx"
        ):
            data.paragraphs.setdefault(tid, []).append((idx, text, part, page))
    _check_passages(data, {v: k for k, v in ctx.ids.items()}, report)
    _check_text(data, ctx, report)
    covered = sum(t - f + 1 for _, _, f, t, kind in data.passages if kind == "commentary")
    minimum = source.extra.get("min_coverage")
    if isinstance(minimum, int) and ctx.profile == "full":
        report.check(covered >= minimum, f"{data.where}: covers {covered}, min_coverage {minimum}")
    report.info.append(f"{data.where}: {len(data.passages):,} passages, {covered:,} verses covered")
    try:
        install_into_core_copy(ctx.core, [(db, source)])
    except (PipelineError, sqlite3.Error) as exc:
        report.check(False, f"{data.where}: install failed: {exc}")


def _check_passages(data: _Pack, keys: dict[int, Key], report: Report) -> None:
    where, pack_id = data.where, require_pack(data.source).id
    report.check(
        [p[0] for p in data.passages] == list(range(1, len(data.passages) + 1)),
        f"{where}: tafsir ids are not 1..{len(data.passages)}",
    )
    last_to = 0
    intros = [p for p in data.passages if p[4] == "introduction"]
    report.check(len(intros) <= 1, f"{where}: {len(intros)} introduction passages, at most 1")
    for tid, pid, vfrom, vto, kind in data.passages:
        ref = f"{where} passage {tid}"
        report.check(pid == pack_id, f"{ref}: pack_id {pid!r}")
        if not report.check(vfrom in keys and vto in keys and vfrom <= vto, f"{ref}: bad verses"):
            continue
        if kind == "introduction":
            report.check(
                tid == 1 and keys[vfrom] == keys[vto] == (1, 1),
                f"{ref}: the introduction must be passage 1, at 1:1",
            )
        elif report.check(kind == "commentary", f"{ref}: kind {kind!r}"):
            report.check(keys[vfrom][0] == keys[vto][0], f"{ref}: crosses surahs")
            report.check(vfrom > last_to, f"{ref}: overlaps or is out of order")
            last_to = vto
        rows = data.paragraphs.get(tid, [])
        report.check(bool(rows), f"{ref}: no paragraphs")
        report.check([r[0] for r in rows] == list(range(len(rows))), f"{ref}: idx not 0..n-1")
        for row in rows:
            _check_paragraph(f"{ref}.{row[0]}", row, report)
    orphans = set(data.paragraphs) - {p[0] for p in data.passages}
    report.check(not orphans, f"{where}: paragraphs of unknown passages {sorted(orphans)[:5]}")


def _check_paragraph(ref: str, row: Paragraph, report: Report) -> None:
    _idx, text, part, page = row
    bad = [t for t in _ANY_TAG.findall(text) if not _ALLOWED_TAG.fullmatch(t)]
    report.check(not bad, f"{ref}: tags outside the subset {sorted(set(bad))[:3]}")
    report.check(bool(subset_letters(text)), f"{ref}: empty paragraph")
    report.check(
        (part is None) == (page is None) and (page is None or page > 0),
        f"{ref}: part {part!r} / page {page!r}",
    )


def _check_text(data: _Pack, ctx: _Context, report: Report) -> None:
    """The stored letters equal the letters of the source sections, passage by passage."""
    assembly, drop = source_assembly(data.source, ctx.ids, ctx.verse_text)
    intro = [assembly.introduction] if assembly.introduction else []
    expected = {
        (ctx.ids[p.first], p.kind): (
            ctx.ids[p.last],
            "".join(source_letters(s.html, drop_footnotes=drop) for s in p.sections),
        )
        for p in intro + assembly.passages
    }
    report.check(
        len(expected) == len(data.passages),
        f"{data.where}: {len(data.passages)} passages, the source gives {len(expected)}",
    )
    for tid, _pid, vfrom, vto, kind in data.passages:
        exp = expected.get((vfrom, kind))
        got = "".join(subset_letters(r[1]) for r in data.paragraphs.get(tid, []))
        if exp is None or exp != (vto, got):
            report.check(False, f"{data.where} passage {tid}: text differs from the source")
            return
