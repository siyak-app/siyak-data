"""Tafsir packs from the Quranpedia dumps (spec §5.2, §6.6; docs/pack-format.md §4.6).

``pipeline/quranpedia.py`` turns a dump into passages; this module converts
their HTML into paragraphs (``pipeline/tafsir_html.py``) and writes
``<id>.sqlite`` with ``pack_info``, ``tafsir`` and ``tafsir_paragraphs``. It
also writes ``reports/tafsir/<id>.json`` with the figures of the coverage
report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.build_translation import require_pack, source_version
from pipeline.errors import PipelineError
from pipeline.fetch import verify_cached
from pipeline.normalize import normalize
from pipeline.qul import load_qul
from pipeline.quranpedia import MIN_GAP_PROBE, Assembly, Key, assemble, load_dump, parse_rules
from pipeline.schema import SCHEMA_VERSION, PackInfo, finalize, new_database, write_pack_info
from pipeline.sources import Source
from pipeline.tafsir_html import convert, skeleton, subset_letters

#: The tafsir tables of content.db (spec §5.2) without foreign keys.
TAFSIR_DDL = """
CREATE TABLE tafsir (
  id          INTEGER PRIMARY KEY,
  pack_id     TEXT NOT NULL,
  verse_from  INTEGER NOT NULL,
  verse_to    INTEGER NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'commentary' CHECK (kind IN ('commentary','introduction')),
  CHECK (verse_to >= verse_from)
);
CREATE TABLE tafsir_paragraphs (
  tafsir_id  INTEGER NOT NULL,
  idx        INTEGER NOT NULL,
  text       TEXT NOT NULL,
  part       TEXT,
  page       INTEGER,
  UNIQUE (tafsir_id, idx)
);
"""

#: Words of a verse looked for in its passage by the quotation check.
QUOTE_WORDS = 3
#: Runs of at least this many consecutive unquoted verses are listed in the report.
UNQUOTED_RUN = 5


@dataclass(frozen=True)
class TafsirRow:
    """One passage as stored: verse ids and paragraphs ``(html, part, page)``."""

    verse_from: int
    verse_to: int
    paragraphs: list[tuple[str, str | None, int | None]]
    kind: str = "commentary"


def is_tafsir_source(source: Source) -> bool:
    """A tafsir pack built from a Quranpedia dump or a QUL database."""
    pack = source.pack
    return (
        pack is not None
        and pack.type == "tafsir"
        and ("quranpedia_book" in source.extra or "qul_file" in source.extra)
    )


def input_file(source: Source) -> str:
    """The pinned file a tafsir pack is built from."""
    if "qul_file" in source.extra:
        return str(source.extra["qul_file"])
    rules = parse_rules(source.extra, str(source.path))
    return f"tafsir-book-{rules.book}.json.gz"


def is_available(source: Source) -> bool:
    """False for an optional source that is not ready (``Source.skipped_optional``)."""
    return not source.skipped_optional()


def source_assembly(
    source: Source, ids: dict[Key, int], verse_text: dict[Key, str]
) -> tuple[Assembly, bool]:
    """The passages of one tafsir source and whether its footnotes are dropped."""
    path = verify_cached(source, input_file(source))
    if "qul_file" in source.extra:
        return load_qul(path, ids), True
    rules = parse_rules(source.extra, str(source.path))
    dump = load_dump(path, ids)
    book_id = dump.book.get("id")
    if book_id != rules.book:
        raise PipelineError(f"{source.path}: the dump is book {book_id}, expected {rules.book}")
    return assemble(dump, rules, verse_text), rules.drop_footnotes


def tafsir_rows(
    source: Source, ids: dict[Key, int], verse_text: dict[Key, str]
) -> tuple[list[TafsirRow], Assembly]:
    """Assemble and convert one book; ``verse_text`` is Tanzil's Simple Clean text."""
    assembly, drop_footnotes = source_assembly(source, ids, verse_text)
    rows = []
    intro = [assembly.introduction] if assembly.introduction else []
    for passage in intro + assembly.passages:
        pieces = [(s.html, s.part, s.page) for s in passage.sections]
        converted = convert(pieces, drop_footnotes=drop_footnotes)
        paragraphs = [
            (html, part if page else None, page) for html, part, page in converted.paragraphs
        ]
        if not paragraphs:
            raise PipelineError(f"{source.id}: passage {passage.first}-{passage.last} has no text")
        rows.append(TafsirRow(ids[passage.first], ids[passage.last], paragraphs, passage.kind))
    return rows, assembly


def write_database(out: Path, info: PackInfo, rows: list[TafsirRow]) -> Path:
    """Write the tafsir SQLite pack."""
    conn = new_database(out)
    write_pack_info(conn, info)
    conn.executescript(TAFSIR_DDL)
    conn.executemany(
        "INSERT INTO tafsir (id, pack_id, verse_from, verse_to, kind) VALUES (?, ?, ?, ?, ?)",
        [(n, info.id, r.verse_from, r.verse_to, r.kind) for n, r in enumerate(rows, start=1)],
    )
    conn.executemany(
        "INSERT INTO tafsir_paragraphs (tafsir_id, idx, text, part, page) VALUES (?, ?, ?, ?, ?)",
        [
            (n, idx, text, part, page)
            for n, r in enumerate(rows, start=1)
            for idx, (text, part, page) in enumerate(r.paragraphs)
        ],
    )
    finalize(conn)
    return out


def quote_check(
    rows: list[TafsirRow], keys: dict[int, Key], verse_text: dict[Key, str]
) -> dict[str, Any]:
    """How many verses are quoted (first words) in their own passage, and the longest
    runs of verses that are not: a sign of commentary filed under the wrong verses."""
    checked = quoted = 0
    unquoted: list[Key] = []
    for row in rows:
        if row.kind != "commentary":
            continue
        text = skeleton(" ".join(html for html, _, _ in row.paragraphs))
        for verse_id in range(row.verse_from, row.verse_to + 1):
            key = keys[verse_id]
            probe = skeleton(" ".join(normalize(verse_text[key]).split()[:QUOTE_WORDS]))
            if len(probe) < MIN_GAP_PROBE:  # too short to tell
                continue
            checked += 1
            if probe in text:
                quoted += 1
            else:
                unquoted.append(key)
    runs: list[list[Key]] = []
    for key in unquoted:
        if runs and runs[-1][-1][0] == key[0] and runs[-1][-1][1] == key[1] - 1:
            runs[-1].append(key)
        else:
            runs.append([key])
    long_runs = sorted((r for r in runs if len(r) >= UNQUOTED_RUN), key=len, reverse=True)
    return {
        "checked": checked,
        "quoted": quoted,
        "unquoted_runs": [f"{r[0][0]}:{r[0][1]}-{r[-1][1]}" for r in long_runs],
    }


def coverage(
    source: Source,
    rows: list[TafsirRow],
    assembly: Assembly,
    ids: dict[Key, int],
    verse_text: dict[Key, str],
) -> dict[str, Any]:
    """The figures of one pack for the coverage report."""
    keys = {v: k for k, v in ids.items()}
    commentary = [r for r in rows if r.kind == "commentary"]
    covered = sum(r.verse_to - r.verse_from + 1 for r in commentary)
    sizes = sorted(commentary, key=lambda r: r.verse_to - r.verse_from, reverse=True)[:5]
    paragraphs = [p for r in rows for p in r.paragraphs]
    return {
        "id": require_pack(source).id,
        "book": (
            f"Quranpedia book {source.extra['quranpedia_book']}"
            if "quranpedia_book" in source.extra
            else f"QUL resource {source.extra.get('qul_resource')}"
        ),
        "passages": len(commentary),
        "introduction_paragraphs": sum(len(r.paragraphs) for r in rows if r.kind != "commentary"),
        "headings": assembly.headings,
        "paragraphs": len(paragraphs),
        "paragraphs_without_page": sum(1 for p in paragraphs if p[2] is None),
        "letters": sum(len(subset_letters(p[0])) for p in paragraphs),
        "verses_covered": covered,
        "gaps": [f"{s}:{a}" for s, a in assembly.gaps],
        "gap_merged": [f"{s}:{a}" for s, a in assembly.gap_merged],
        "largest": [
            f"{keys[r.verse_from][0]}:{keys[r.verse_from][1]}-{keys[r.verse_to][1]}" for r in sizes
        ],
        "copies": dict(sorted(assembly.copies.items())),
        "excluded": assembly.excluded,
        "moved": assembly.moved,
        "page_artifacts": assembly.page_artifacts,
        "ayahs_field_mismatches": assembly.ayahs_field_mismatches,
        "accounting": assembly.accounting,
        "quotes": quote_check(rows, keys, verse_text),
    }


def build_tafsir_pack(
    source: Source,
    ids: dict[Key, int],
    verse_text: dict[Key, str],
    out_dir: Path,
    built_at: str,
) -> Path:
    """Build ``<out_dir>/<id>.sqlite`` and ``<out_dir>/reports/tafsir/<id>.json``."""
    pack = require_pack(source)
    if pack.type != "tafsir":
        raise PipelineError(f"{source.path}: pack type is '{pack.type}', not 'tafsir'")
    rows, assembly = tafsir_rows(source, ids, verse_text)
    info = PackInfo(
        pack.id, pack.type, pack.version, SCHEMA_VERSION, built_at, source_version(source)
    )
    out = write_database(out_dir / f"{pack.id}.sqlite", info, rows)
    reports = out_dir / "reports" / "tafsir"
    reports.mkdir(parents=True, exist_ok=True)
    figures = coverage(source, rows, assembly, ids, verse_text)
    (reports / f"{pack.id}.json").write_text(
        json.dumps(figures, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return out


def write_reports(out_dir: Path) -> list[Path]:
    """``reports/tafsir-coverage.md`` and ``reports/tafsir-sizes.md`` from the JSON figures."""
    figures = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((out_dir / "reports" / "tafsir").glob("*.json"))
    ]
    if not figures:
        return []
    coverage_md = out_dir / "reports" / "tafsir-coverage.md"
    coverage_md.write_text(_coverage_markdown(figures), encoding="utf-8")
    sizes_md = out_dir / "reports" / "tafsir-sizes.md"
    sizes_md.write_text(_sizes_markdown(figures, out_dir), encoding="utf-8")
    return [coverage_md, sizes_md]


def _coverage_markdown(figures: list[dict[str, Any]]) -> str:
    lines = [
        "# Tafsir coverage",
        "",
        "Verses covered = verses inside a passage. Quoted = verses whose first words occur",
        "in their own passage (a low share, or a long run of unquoted verses, points to",
        "commentary filed under the wrong verses in the source).",
        "",
        "| Pack | Source | Passages | Verses covered | Gaps | Gap merges (K4) | Quoted "
        "| Paragraphs without page |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in figures:
        q = f["quotes"]
        share = q["quoted"] / q["checked"] if q["checked"] else 0
        lines.append(
            f"| `{f['id']}` | {f['book']} | {f['passages']:,} | {f['verses_covered']:,} "
            f"| {len(f['gaps'])} | {len(f['gap_merged'])} | {share:.1%} "
            f"| {f['paragraphs_without_page']:,} of {f['paragraphs']:,} |"
        )
    for f in figures:
        acc = f["accounting"]
        lines += [
            "",
            f"## `{f['id']}` ({f['book']})",
            "",
            f"- Letters: source {acc['source']:,} = stored {acc['stored']:,} + repeated "
            f"{acc['repeated']:,} + dropped copies {acc['copies']:,} + editor footnotes "
            f"{acc['footnotes']:,} + edition matter {acc['excluded']:,}",
            f"- Largest passages: {', '.join(f['largest'])}",
            f"- Copies and duplicates: {_kv(f['copies'])}",
            f"- Edition matter left out: {_kv(f['excluded'])}",
            f"- Author's introduction (kind introduction, at 1:1): {_kv(f['moved'])}, "
            f"{f['introduction_paragraphs']:,} paragraphs",
            f"- Edition headings (passage_headings): {_kv(f['headings'])}",
            f"- Page artifacts kept (pieces that are only a page number): {f['page_artifacts']}",
            f"- `ayahs` field not naming the verse: {f['ayahs_field_mismatches']:,} pieces",
            f"- Gaps ({len(f['gaps'])}): {_list(f['gaps'])}",
            f"- Gap merges ({len(f['gap_merged'])}): {_list(f['gap_merged'])}",
            f"- Runs of 5+ unquoted verses: {_list(f['quotes']['unquoted_runs'])}",
        ]
    return "\n".join(lines) + "\n"


def _sizes_markdown(figures: list[dict[str, Any]], out_dir: Path) -> str:
    lines = [
        "# Tafsir pack sizes",
        "",
        "| Pack | Characters (letters) | SQLite | `.sqlite.zst` (download) |",
        "|---|---|---|---|",
    ]
    total = [0, 0]
    for f in figures:
        db = out_dir / f"{f['id']}.sqlite"
        zst = out_dir / f"{f['id']}.sqlite.zst"
        sizes = [db.stat().st_size if db.exists() else 0, zst.stat().st_size if zst.exists() else 0]
        total = [total[0] + sizes[0], total[1] + sizes[1]]
        mb = f"{sizes[0] / 1e6:.1f} MB | {sizes[1] / 1e6:.2f} MB"
        lines.append(f"| `{f['id']}` | {f['letters']:,} | {mb} |")
    lines.append(f"| **total** | | {total[0] / 1e6:.1f} MB | {total[1] / 1e6:.2f} MB |")
    return "\n".join(lines) + "\n"


def _kv(values: dict[str, int]) -> str:
    return "; ".join(f"{k}: {v:,}" for k, v in values.items()) or "none"


def _list(values: list[str], limit: int = 40) -> str:
    shown = ", ".join(values[:limit])
    return (shown + (f" … ({len(values) - limit} more)" if len(values) > limit else "")) or "none"
