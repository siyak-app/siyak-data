# ar.abussuud: Irshād al-ʿAql al-Salīm (Abū al-Suʿūd)

| | |
|---|---|
| Work | Irshād al-ʿAql al-Salīm ilā Mazāyā al-Kitāb al-Karīm (إرشاد العقل السليم إلى مزايا الكتاب الكريم) |
| Author | Abū al-Suʿūd Muḥammad ibn Muḥammad al-ʿImādī (Ebussuud Efendi) (d. 982/1574) |
| Edition | دار إحياء التراث العربي - بيروت |
| Source | Quranpedia.net data dumps, book 37: `tafsir-book-37.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.abussuud` tafsir pack (`ar.abussuud.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 37), verbatim:

| Field | Value |
|---|---|
| `name` | إرشاد العقل السليم إلى مزايا الكتاب الكريم |
| `short_name` | تفسير أبي السعود |
| `author.full_name` | أبو السعود محمد بن محمد بن مصطفى  العمادي |
| `mohaqeq` | — |
| `nasher` | دار إحياء التراث العربي - بيروت |
| `edition` | — |
| `publish_year` | — |
| `parts` | 1 |
| `language` | ar |

Measured in the pinned file before conversion: 6,205 of 6,236
verses have their own entry; 6,197 passages after merging consecutive
verses with identical text; 6.3 million characters of text;
3 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Edition matter and the author's introduction

None found: the dump holds only the author's text (M1c review).

After conversion: 6,178 passages covering 6,227 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: editor footnotes. Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
