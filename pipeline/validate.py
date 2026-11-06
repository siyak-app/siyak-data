"""Validation gates (spec §15.2) for the files in dist/.

Every gate either passes or adds a failure that names the exact place
(surah:ayah, table, pack) with the expected and actual value. All gates run
and all failures are reported together; any failure makes ``validate`` exit
non-zero.

Profiles: ``full`` expects the whole Quran (114 surahs, 6,236 verses).
``fixtures`` expects the surahs present in the fixture text, with counts taken
from the (complete) Tanzil metadata, and runs the same checks otherwise.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from pipeline.build import TANZIL, morphology_sources, tafsir_sources, translation_sources
from pipeline.build_core import CORE_VERSION, METADATA, UTHMANI
from pipeline.build_translation import require_pack, source_version
from pipeline.errors import PipelineError
from pipeline.fetch import verify_cached
from pipeline.gates import Report, install_into_core_copy, unpack_published
from pipeline.install import check_pack_structure
from pipeline.normalize import REMOVALS, normalize, rule_counts
from pipeline.paths import repo_root
from pipeline.schema import SCHEMA_VERSION, apply_content_schema, read_pack_info, schema_shape
from pipeline.sources import Source, load_all
from pipeline.tanzil import parse_metadata
from pipeline.validate_morphology import check_alignment, check_morphology_pack
from pipeline.validate_tafsir import check_tafsir_packs

FULL_SURAHS = 114
FULL_VERSES = 6236
JUZ_COUNT = 30
NO_BISMILLAH = {1, 9}
#: Characters that must never occur in text_clean (normalization rules N1–N4).
HARAKAT_RULES = ("N1", "N2", "N3", "N4")
VECTORS = repo_root() / "tests" / "normalize_vectors.json"


def _forbidden_clean_chars() -> set[str]:
    return {chr(code) for rule in HARAKAT_RULES for span in REMOVALS[rule] for code in span}


def _check_verse_texts(
    conn: sqlite3.Connection,
    verses: list[tuple[int, int, int, int, str, str]],
    report: Report,
    *,
    profile: str,
) -> None:
    """Juz order, non-empty texts, harakat-free text_clean and the normalized FTS index."""
    last_juz = 1
    forbidden = _forbidden_clean_chars()
    for _vid, surah, ayah, juz, uthmani, clean in verses:
        ref = f"{surah}:{ayah}"
        report.check(1 <= juz <= JUZ_COUNT, f"{ref}: juz {juz} outside 1..{JUZ_COUNT}")
        report.check(juz >= last_juz, f"{ref}: juz {juz} after juz {last_juz}")
        last_juz = juz
        report.check(bool(str(uthmani).strip()), f"{ref}: empty text_uthmani")
        report.check(bool(str(clean).strip()), f"{ref}: empty text_clean")
        bad = sorted({f"U+{ord(ch):04X}" for ch in str(clean) if ch in forbidden})
        report.check(not bad, f"{ref}: text_clean contains harakat/marks {bad}")
    if profile == "full":
        juzs = {v[3] for v in verses}
        report.check(juzs == set(range(1, JUZ_COUNT + 1)), f"juz: found {len(juzs)} distinct")

    fts = dict(conn.execute("SELECT rowid, text_norm FROM verses_fts").fetchall())
    report.check(len(fts) == len(verses), f"verses_fts: {len(fts)} rows, expected {len(verses)}")
    for vid, surah, ayah, _j, _u, clean in verses:
        report.check(
            fts.get(vid) == normalize(str(clean)),
            f"{surah}:{ayah}: verses_fts text differs from normalize(text_clean)",
        )


def check_content_meta(conn: sqlite3.Connection, report: Report, *, tanzil_version: str) -> None:
    """core.db states its core_version and the Tanzil text version (pack-format §3)."""
    try:
        meta = dict(conn.execute("SELECT key, value FROM content_meta").fetchall())
    except sqlite3.Error as exc:
        report.check(False, f"core.db: content_meta unreadable: {exc}")
        return
    expected = {"core_version": CORE_VERSION, "tanzil_version": tanzil_version}
    for key, value in expected.items():
        report.check(
            meta.get(key) == value,
            f"core.db: content_meta '{key}' is {meta.get(key)!r}, expected {value!r}",
        )
    extra = sorted(set(meta) - set(expected))
    report.check(not extra, f"core.db: content_meta has unknown keys {extra}")


def check_core(
    core: Path, report: Report, *, profile: str, expected: dict[int, int], tanzil_version: str
) -> None:
    """Gates for core.db. ``expected`` maps every surah that must have verses to its ayah count."""
    conn = sqlite3.connect(core)
    fresh = sqlite3.connect(":memory:")
    apply_content_schema(fresh)
    core_shape, fresh_shape = schema_shape(conn), schema_shape(fresh)
    for key in sorted(set(core_shape) | set(fresh_shape)):
        report.check(
            core_shape.get(key) == fresh_shape.get(key),
            f"core.db: {key} differs from schema/content.sql",
        )
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    report.check(version == SCHEMA_VERSION, f"core.db: user_version {version} != {SCHEMA_VERSION}")
    check_content_meta(conn, report, tanzil_version=tanzil_version)

    surahs = conn.execute(
        "SELECT number, name_tr, ayah_count, bismillah FROM surahs ORDER BY number"
    ).fetchall()
    numbers = [s[0] for s in surahs]
    report.check(
        numbers == list(range(1, FULL_SURAHS + 1)),
        f"surahs: expected numbers 1..{FULL_SURAHS}, found {len(numbers)} rows",
    )
    for number, name_tr, _count, _b in surahs:
        report.check(bool(str(name_tr).strip()), f"surah {number}: empty name_tr")

    verses = conn.execute(
        "SELECT id, surah, ayah, juz, text_uthmani, text_clean FROM verses ORDER BY id"
    ).fetchall()
    total = sum(expected.values())
    if profile == "full":
        report.check(total == FULL_VERSES, f"metadata: {total} verses, expected {FULL_VERSES}")
    report.check(len(verses) == total, f"verses: {len(verses)} rows, expected {total}")

    by_surah: dict[int, list[int]] = {}
    for _id, surah, ayah, *_rest in verses:
        by_surah.setdefault(surah, []).append(ayah)
    report.check(
        sorted(by_surah) == sorted(expected),
        f"verses: surahs present {sorted(by_surah)[:10]}…, expected {sorted(expected)[:10]}…",
    )
    for surah, count in expected.items():
        ayahs = by_surah.get(surah, [])
        if ayahs != list(range(1, count + 1)):
            gap = next(
                (i + 1 for i, a in enumerate(ayahs) if a != i + 1), min(len(ayahs), count) + 1
            )
            report.check(
                False,
                f"surah {surah}: ayahs not contiguous 1..{count} "
                f"(found {len(ayahs)}, first problem at ayah {gap})",
            )
    ids = [v[0] for v in verses]
    keys = [(v[1], v[2]) for v in verses]
    report.check(keys == sorted(keys), "verses: ids are not in (surah, ayah) order")
    if profile == "full":
        report.check(ids == list(range(1, FULL_VERSES + 1)), "verses: ids are not 1..6236")

    for number, _n, _c, bismillah in surahs:
        if number in expected:
            report.check(
                (bismillah is None) == (number in NO_BISMILLAH),
                f"surah {number}: bismillah is {'missing' if bismillah is None else 'present'}",
            )

    _check_verse_texts(conn, verses, report, profile=profile)

    counts = rule_counts(str(v[5]) for v in verses)
    report.info.append(
        "normalization of text_clean, characters changed per rule: "
        + ", ".join(f"{rule} {counts[rule]:,}" for rule in sorted(counts))
    )
    notices = {row[0]: row[1] for row in conn.execute("SELECT id, body FROM notices")}
    for required in ("tanzil.text.uthmani", "tanzil.text.simple-clean", "tanzil.metadata"):
        report.check(bool(notices.get(required, "").strip()), f"notices: '{required}' missing")
    conn.close()


def check_translation_rows(
    rows: Iterable[tuple[int, str]], verse_ids: set[int], where: str, report: Report
) -> None:
    """A translation must have exactly one non-empty text per verse."""
    seen: Counter[int] = Counter()
    for verse_id, text in rows:
        seen[verse_id] += 1
        report.check(bool(str(text).strip()), f"{where}: verse id {verse_id} has empty text")
    report.check(
        len(seen) == len(verse_ids),
        f"{where}: {sum(seen.values())} rows, expected {len(verse_ids)}",
    )
    missing, extra = verse_ids - set(seen), set(seen) - verse_ids
    report.check(not missing, f"{where}: missing verse ids, first {sorted(missing)[:5]}")
    report.check(not extra, f"{where}: verse ids not in core.db, first {sorted(extra)[:5]}")
    dup = [v for v, n in seen.items() if n > 1]
    report.check(not dup, f"{where}: duplicate verse ids {dup[:5]}")


def check_translation_pack(
    path: Path, source: Source, verse_ids: set[int], core: Path, report: Report
) -> None:
    """Structure, pack_info, rows and installability of one translation pack."""
    pack = require_pack(source)
    where = path.name
    if not report.check(path.exists(), f"{where}: not built"):
        return
    conn = sqlite3.connect(path)
    try:
        check_pack_structure(conn, pack.type)
        info = read_pack_info(conn)
    except (PipelineError, ValueError, sqlite3.Error) as exc:
        report.check(False, f"{where}: {exc}")
        return
    expected = (pack.id, pack.type, pack.version, SCHEMA_VERSION, source_version(source))
    actual = (info.id, info.type, info.version, info.schema_version, info.source_version)
    report.check(actual == expected, f"{where}: pack_info {actual} != source.toml {expected}")
    rows = conn.execute("SELECT verse_id, text FROM translations").fetchall()
    ids = {r[0] for r in conn.execute("SELECT DISTINCT pack_id FROM translations")}
    report.check(ids <= {pack.id}, f"{where}: rows with other pack_id {sorted(ids)}")
    conn.close()
    check_translation_rows(rows, verse_ids, where, report)
    try:
        install_into_core_copy(core, [(path, source)])
    except (PipelineError, sqlite3.Error) as exc:
        report.check(False, f"{where}: install failed: {exc}")


def check_sources(sources: list[Source], report: Report) -> None:
    """Every pinned input still matches, and pack metadata is complete."""
    for source in sources:
        if source.skipped_optional():
            report.info.append(f"{source.id}: optional source not ready (cache or pin), skipped")
            continue
        for f in source.files:
            try:
                verify_cached(source, f.name)
            except PipelineError as exc:
                report.check(False, str(exc))
        if source.pack is not None and source.pack.publish:
            pack = source.pack
            report.check(bool(pack.license.strip()), f"{source.path}: publish=true needs license")
            problem = source.permission_problem()
            report.check(problem is None, str(problem))
            report.check(
                source.terms is None or pack.license_terms is not None,
                f"{source.path}: source has terms of use, so [pack.license_terms] is required",
            )
            if pack.type == "vectors" and pack.meta.get("backend") == "api":
                report.check(
                    pack.terms_ack,
                    f"{source.path}: searches go to the provider, so terms_ack = true is required",
                )
                report.check(
                    any(f.name == "vectors.npy" for f in source.files),
                    f"{source.path}: an api pack is published from pinned vectors "
                    "(export-vectors), a release has no key",
                )


def check_vectors(report: Report) -> None:
    """The shared normalization vectors pass."""
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))["vectors"]
    for v in vectors:
        report.check(
            normalize(v["input"]) == v["expected"],
            f"normalize_vectors {v['id']}: expected {v['expected']!r}",
        )
    report.info.append(f"normalization vectors: {len(vectors)} checked")


def run_validate(dist: Path, profile: str) -> Report:
    """Run every gate on ``dist`` and return the report."""
    report = Report()
    sources = load_all()
    tanzil = next((s for s in sources if s.id == TANZIL), None)
    if tanzil is None:
        raise PipelineError("no 'tanzil' source found")
    check_sources(sources, report)
    check_vectors(report)
    if report.failures:
        return report
    metadata = parse_metadata(verify_cached(tanzil, METADATA))
    core = dist / "core.db"
    if not report.check(core.exists(), f"{core}: not built; run 'siyak-data build'"):
        return report
    with sqlite3.connect(core) as conn:
        present = {r[0] for r in conn.execute("SELECT DISTINCT surah FROM verses")}
        verse_ids = {r[0] for r in conn.execute("SELECT id FROM verses")}
    wanted = {s.number for s in metadata.surahs} if profile == "full" else present
    expected = {s.number: s.ayah_count for s in metadata.surahs if s.number in wanted}
    check_core(
        core,
        report,
        profile=profile,
        expected=expected,
        tanzil_version=tanzil.file(UTHMANI).version,
    )

    for source in translation_sources(sources):
        pack = require_pack(source)
        with tempfile.TemporaryDirectory(prefix="siyak-validate-") as tmp:
            published = unpack_published(dist / f"{pack.id}.sqlite", Path(tmp), report)
            if published is not None:
                check_translation_pack(published, source, verse_ids, core, report)
        if pack.bundled:
            with sqlite3.connect(core) as conn:
                rows = conn.execute(
                    "SELECT verse_id, text FROM translations WHERE pack_id = ?", (pack.id,)
                ).fetchall()
                bundled = conn.execute(
                    "SELECT bundled FROM packs WHERE id = ?", (pack.id,)
                ).fetchone()
            check_translation_rows(rows, verse_ids, f"core.db translations {pack.id}", report)
            report.check(
                bundled == (1,), f"core.db: packs row for {pack.id} missing or not bundled"
            )
    for source in morphology_sources(sources):
        # A broken core.db or pack must show up as gate failures, not a crash.
        for gate in (check_alignment, check_morphology_pack):
            try:
                gate(dist, source, core, report)
            except PipelineError as exc:
                report.check(False, f"{require_pack(source).id}: {exc}")
    check_tafsir_packs(dist, tafsir_sources(sources), tanzil, core, report, profile=profile)
    for path in sorted(dist.glob("*.db")) + sorted(dist.glob("*.sqlite")):
        report.info.append(f"{path.name}: {path.stat().st_size:,} bytes")
    report.info.append(
        f"profile {profile}: {len(expected)} surahs, {sum(expected.values())} verses"
    )
    return report


def print_report(report: Report, out: Path | None = None) -> None:
    """Print info lines and failures; optionally write them to ``out``."""
    lines = [f"info   {line}" for line in report.info]
    lines += [f"FAIL   {line}" for line in report.failures]
    lines.append(
        f"{len(report.failures)} gate failure(s)" if report.failures else "all gates passed"
    )
    text = "\n".join(lines)
    print(text)
    if out is not None:
        out.write_text(text + "\n", encoding="utf-8")
