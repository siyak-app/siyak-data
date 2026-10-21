# ar.baghawi: Maʿālim al-Tanzīl (al-Baghawī)

| | |
|---|---|
| Work | Maʿālim al-Tanzīl (معالم التنزيل) |
| Author | al-Ḥusayn ibn Masʿūd al-Baghawī (d. 516/1122) |
| Edition | دار طيبة للنشر والتوزيع · الرابعة · 1417; editor (محقق): محمد عبد الله النمر |
| Source | Quranpedia.net data dumps, book 2: `tafsir-book-2.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.baghawi` tafsir pack (`ar.baghawi.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 2), verbatim:

| Field | Value |
|---|---|
| `name` | معالم التنزيل |
| `short_name` | تفسير البغوي |
| `author.full_name` | محيي السنة، أبو محمد الحسين بن مسعود بن محمد بن الفراء البغوي الشافعي |
| `mohaqeq` | محمد عبد الله النمر |
| `nasher` | دار طيبة للنشر والتوزيع |
| `edition` | الرابعة |
| `publish_year` | 1417 |
| `parts` | 8 |
| `language` | ar |

Measured in the pinned file before conversion: 6,236 of 6,236
verses have their own entry; 2,439 passages after merging consecutive
verses with identical text; 8.7 million characters of text;
2,883 editor-footnote blocks.


Other Quranpedia ids considered:

- 261: same work, Dār Iḥyāʾ al-Turāth al-ʿArabī 1420, ed. ʿAbd al-Razzāq al-Mahdī. Rejected: only 3,134 of 6,236 verses have an entry.

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| left out | 114:1-114:6 | 1 | 5–32 | Editors' introduction (مقدمة التحقيق), study of the author, description and plates of the manuscripts |
| moved to 1:1 | 114:1-114:6 | 1 | 33–47 | Author's introduction |

After conversion: 2,434 passages covering 6,236 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: editor footnotes (manuscript variants, hadith references). Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
