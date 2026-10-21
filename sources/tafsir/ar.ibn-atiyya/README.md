# ar.ibn-atiyya: al-Muḥarrar al-Wajīz (Ibn ʿAṭiyya)

| | |
|---|---|
| Work | al-Muḥarrar al-Wajīz fī Tafsīr al-Kitāb al-ʿAzīz (المحرر الوجيز فى تفسير الكتاب العزيز) |
| Author | ʿAbd al-Ḥaqq ibn Ghālib ibn ʿAṭiyya (d. 541/1147) |
| Edition | دار الكتب العلمية - بيروت · الأولى · 1422 - 2001; editor (محقق): عبد السلام عبد الشافي محمد |
| Source | Quranpedia.net data dumps, book 350: `tafsir-book-350.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.ibn-atiyya` tafsir pack (`ar.ibn-atiyya.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 350), verbatim:

| Field | Value |
|---|---|
| `name` | المحرر الوجيز فى تفسير الكتاب العزيز |
| `short_name` | تفسير ابن عطية |
| `author.full_name` | أبو محمد عبد الحق بن غالب بن عبد الرحمن بن تمام بن عطية الأندلسي المحاربي |
| `mohaqeq` | عبد السلام عبد الشافي محمد |
| `nasher` | دار الكتب العلمية - بيروت |
| `edition` | الأولى |
| `publish_year` | 1422 - 2001 |
| `parts` | 1 |
| `language` | ar |

Measured in the pinned file before conversion: 6,236 of 6,236
verses have their own entry; 1,580 passages after merging consecutive
verses with identical text; 7.0 million characters of text;
23 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Conversion

- Footnotes: editor footnotes. Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
