# ar.nasafi: Madārik al-Tanzīl (al-Nasafī)

| | |
|---|---|
| Work | Madārik al-Tanzīl wa-Ḥaqāʾiq al-Taʾwīl (مدارك التنزيل وحقائق التأويل) |
| Author | ʿAbd Allāh ibn Aḥmad al-Nasafī (d. 710/1310) |
| Edition | دار الكلم الطيب، بيروت · الأولى · 1419 - 1998 |
| Source | Quranpedia.net data dumps, book 26: `tafsir-book-26.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.nasafi` tafsir pack (`ar.nasafi.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 26), verbatim:

| Field | Value |
|---|---|
| `name` | مدارك التنزيل وحقائق التأويل |
| `short_name` | تفسير النسفي |
| `author.full_name` | أبو البركات عبد الله بن أحمد بن محمود حافظ الدين النسفي |
| `mohaqeq` | — |
| `nasher` | دار الكلم الطيب، بيروت |
| `edition` | الأولى |
| `publish_year` | 1419 - 1998 |
| `parts` | 3 |
| `language` | ar |

Measured in the pinned file before conversion: 6,236 of 6,236
verses have their own entry; 6,135 passages after merging consecutive
verses with identical text; 3.5 million characters of text;
0 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`. "introduction"
marks the author's own introduction, stored as a separate `kind = "introduction"`
passage at 1:1:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| left out | 114:6 | 3 | 701–701 (from «تم بعون الله تعالى طبع») | Printer's closing line (تم بعون الله تعالى طبع كتاب تفسير النسفى) |
| introduction | 33:63 | 1 | 23–25 | Author's preface |

After conversion: 6,135 passages covering 6,236 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: none in this edition. Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
