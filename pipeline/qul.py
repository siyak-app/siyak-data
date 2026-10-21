"""Tafsirs from the Quranic Universal Library (QUL, Tarteel) → passages (spec §6.6).

A QUL tafsir database has one row per verse: ``ayah_key``, ``group_ayah_key``,
``from_ayah``, ``to_ayah``, ``ayah_keys`` and ``text`` (HTML). The first verse of
a group holds the text; the other verses of the group have empty text and name
the first in ``group_ayah_key``. Each group becomes one passage, so the ranges
come from the source itself; a group whose text has no letters (an empty
``<div>``) is a gap. The structure is checked, not repaired: a group
that crosses a surah, a member outside its group, or text on a member row
fails the build.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from pipeline.errors import PipelineError
from pipeline.quranpedia import Assembly, Key, Passage, Piece, Section
from pipeline.tafsir_html import source_letters

COLUMNS = ("ayah_key", "group_ayah_key", "from_ayah", "to_ayah", "ayah_keys", "text")


def _key(text: str, where: str) -> Key:
    surah, _, ayah = str(text).partition(":")
    if not (surah.isdigit() and ayah.isdigit()):
        raise PipelineError(f"{where}: '{text}' is not a verse key")
    return int(surah), int(ayah)


def load_qul(path: Path, ids: dict[Key, int]) -> Assembly:
    """Read a QUL tafsir database and return its passages."""
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
        columns = tuple(r[1] for r in conn.execute("PRAGMA table_info(tafsir)"))
        if columns != COLUMNS:
            raise PipelineError(
                f"{path.name}: table tafsir has columns {columns}, expected {COLUMNS}"
            )
        rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM tafsir").fetchall()
    heads: dict[Key, Passage] = {}
    members: dict[Key, Key] = {}
    empty: list[Key] = []
    for ayah_key, group_key, first, last, keys, text in rows:
        where = f"{path.name} {ayah_key}"
        key, group = _key(ayah_key, where), _key(group_key, where)
        if key not in ids:
            raise PipelineError(f"{where}: unknown verse")
        if key == group:
            lo, hi = _key(first, where), _key(last, where)
            if lo != key or hi[0] != key[0] or hi < lo:
                raise PipelineError(f"{where}: group {first}-{last} is not a range from this verse")
            expected = ",".join(f"{key[0]}:{a}" for a in range(lo[1], hi[1] + 1))
            if str(keys) != expected:
                raise PipelineError(f"{where}: ayah_keys {keys!r} do not match {first}-{last}")
            if not source_letters(str(text or ""), drop_footnotes=False):
                empty.append(key)  # e.g. 34:54 holds only an empty <div>: a gap, reported
                continue
            passage = Passage(lo, hi)
            passage.sections = [Section(Piece(str(text), None, None), str(text), None, None)]
            heads[key] = passage
        else:
            if str(text or "").strip():
                raise PipelineError(f"{where}: a verse inside group {group_key} has its own text")
            members[key] = group
    for key, group in members.items():
        head = heads.get(group)
        if group in empty:
            continue
        if head is None or not head.first <= key <= head.last:
            raise PipelineError(f"{path.name} {key[0]}:{key[1]}: outside its group {group}")
    passages = sorted(heads.values(), key=lambda p: ids[p.first])
    covered = {(p.first[0], a) for p in passages for a in range(p.first[1], p.last[1] + 1)}
    stored = sum(len(source_letters(p.sections[0].html, drop_footnotes=False)) for p in passages)
    accounting = {"source": stored, "excluded": 0, "footnotes": 0, "copies": 0}
    accounting |= {"stored": stored, "repeated": 0}
    return Assembly(
        passages=passages,
        gaps=sorted(set(ids) - covered),
        gap_merged=[],
        excluded={},
        moved={},
        copies=Counter(),
        copy_letters=0,
        page_artifacts=0,
        ayahs_field_mismatches=0,
        accounting=accounting,
    )
