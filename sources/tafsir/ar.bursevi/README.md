# ar.bursevi: Rūḥ al-Bayān (Bursawī)

| | |
|---|---|
| Work | Rūḥ al-Bayān (روح البيان) |
| Author | İsmāʿīl Ḥaqqī Bursawī (İsmail Hakkı Bursevî) (d. 1137/1725) |
| Edition | دار الفكر - بيروت |
| Source | Quranpedia.net data dumps, book 336: `tafsir-book-336.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.bursevi` tafsir pack (`ar.bursevi.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 336), verbatim:

| Field | Value |
|---|---|
| `name` | روح البيان |
| `short_name` | روح البيان |
| `author.full_name` | إسماعيل حقي بن مصطفى الإستانبولي الحنفي الخلوتي , المولى أبو الفداء |
| `mohaqeq` | — |
| `nasher` | دار الفكر - بيروت |
| `edition` | — |
| `publish_year` | — |
| `parts` | 1 |
| `language` | ar |

Measured in the pinned file before conversion: 6,236 of 6,236
verses have their own entry; 3,566 passages after merging consecutive
verses with identical text; 22.1 million characters of text;
613 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Conversion

- Footnotes: footnotes of the printed edition (e.g. references to the Mathnawī, in Persian). Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
