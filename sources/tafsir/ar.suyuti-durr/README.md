# ar.suyuti-durr: al-Durr al-Manthūr (al-Suyūṭī)

| | |
|---|---|
| Work | al-Durr al-Manthūr fī al-Tafsīr bi-l-Maʾthūr (الدر المنثور في التأويل بالمأثور) |
| Author | Jalāl al-Dīn al-Suyūṭī (d. 911/1505) |
| Edition | دار الفكر - بيروت · 1432 - 2011 |
| Source | Quranpedia.net data dumps, book 273: `tafsir-book-273.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.suyuti-durr` tafsir pack (`ar.suyuti-durr.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 273), verbatim:

| Field | Value |
|---|---|
| `name` | الدر المنثور في التأويل بالمأثور |
| `short_name` | الدر المنثور |
| `author.full_name` | جلال الدين عبد الرحمن بن أبي بكر بن محمد ابن سابق الدين الخضيري السيوطي |
| `mohaqeq` | — |
| `nasher` | دار الفكر - بيروت |
| `edition` | — |
| `publish_year` | 1432 - 2011 |
| `parts` | 8 |
| `language` | ar |

Measured in the pinned file before conversion: 4,427 of 6,236
verses have their own entry; 4,391 passages after merging consecutive
verses with identical text; 13.5 million characters of text;
1 editor-footnote blocks.


Other Quranpedia ids considered:

- 1499: same title, full coverage, but no edition, publisher or editor in the metadata, so the edition cannot be verified (spec §6.6).

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| moved to 1:1 | 114:6 | 1 | 9–19 | Author's introduction (مقدمة المؤلف) |

After conversion: 2,785 passages covering 5,483 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: editor footnotes. Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
