# ar.razi: Mafātīḥ al-Ghayb (al-Rāzī)

| | |
|---|---|
| Work | Mafātīḥ al-Ghayb (al-Tafsīr al-Kabīr) (مفاتيح الغيب) |
| Author | Fakhr al-Dīn al-Rāzī (d. 606/1210) |
| Edition | دار إحياء التراث العربي - بيروت · الثالثة · 1420 |
| Source | Quranpedia.net data dumps, book 352: `tafsir-book-352.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.razi` tafsir pack (`ar.razi.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 352), verbatim:

| Field | Value |
|---|---|
| `name` | مفاتيح الغيب |
| `short_name` | تفسير الرازي |
| `author.full_name` | أبو عبد الله محمد بن عمر (خطيب الري) بن الحسن بن الحسين التيمي الرازي |
| `mohaqeq` | — |
| `nasher` | دار إحياء التراث العربي - بيروت |
| `edition` | الثالثة |
| `publish_year` | 1420 |
| `parts` | 1 |
| `language` | ar |

Measured in the pinned file before conversion: 6,236 of 6,236
verses have their own entry; 2,666 passages after merging consecutive
verses with identical text; 26.2 million characters of text;
349 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| left out | 114:6 | 32 | 379–380 | Printer's colophon (خاتمة الطبع) |

After conversion: 2,666 passages covering 6,236 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: editor footnotes. Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
