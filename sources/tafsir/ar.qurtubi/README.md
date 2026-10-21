# ar.qurtubi: al-Jāmiʿ li-Aḥkām al-Qurʾān (al-Qurṭubī)

| | |
|---|---|
| Work | al-Jāmiʿ li-Aḥkām al-Qurʾān (الجامع لأحكام القرآن) |
| Author | Muḥammad ibn Aḥmad al-Qurṭubī (d. 671/1273) |
| Edition | not stated by the source |
| Source | Quranic Universal Library (QUL, Tarteel), tafsir resource #23: `ar-tafseer-al-qurtubi.db.zip` (file dated 2025-05-26), downloaded by hand on 2026-10-21 |
| Used in | the `ar.qurtubi` tafsir pack, **not published** (`publish = false`) |

al-Qurṭubī's tafsir is not among the Quranpedia tafsir dumps (book 367 is Makkī
al-Qaysī's *al-Hidāya*, a different work), so it comes from QUL (spec §6.6).

## Permission (spec §6.6)

QUL states no origin or license for this resource; its FAQ asks users to check
the license of each resource. A written request for the origin of the text
(edition, editor) and for permission to redistribute it unmodified was sent to
Tarteel. Until the reply is recorded in `PERMISSION.md` in this directory:

- `requires_permission = true`: `manifest` refuses `publish = true` and
  `validate` fails if it is set;
- the file is not mirrored, so CI has no copy: `optional = true` makes `fetch`,
  `build` and `validate` skip the pack when the file is not in `.cache/` or not
  pinned. On a maintainer's machine it is built and validated in full.

## Format

One SQLite table `tafsir (ayah_key, group_ayah_key, from_ayah, to_ayah,
ayah_keys, text)`, one row per verse (6,236). The first verse of a group holds
the text (`div.ar`, `p`, and `span.qpc-hafs` for Quran quotations, which become
`span.ayah`); the other verses of the group have empty text. Each group is one
passage (`pipeline/qul.py`); there are no footnotes and no edition matter.

Measured: 3,261 groups (2,100 of one verse, the largest 29), 3,259 passages
after the two empty groups, 6,234 verses covered, 15.2 million letters, all
stored.

## Source issues (not changed; see `docs/upstream/tarteel.md`)

- 34:54 has an empty text (`<div class=ar lang=ar></div>`); its commentary is
  at the start of 35:1, which begins with the text of 34:54.
- 59:19 has an empty text.

Both verses are reported as gaps in the coverage report.
