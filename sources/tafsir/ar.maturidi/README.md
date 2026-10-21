# ar.maturidi: Taʾwīlāt Ahl al-Sunna (al-Māturīdī)

| | |
|---|---|
| Work | Taʾwīlāt Ahl al-Sunna (تأويلات أهل السنة) |
| Author | Abū Manṣūr al-Māturīdī (d. 333/944) |
| Edition | دار الكتب العلمية - بيروت، لبنان · الأولى · 1426; editor (محقق): مجدي محمد باسلوم |
| Source | Quranpedia.net data dumps, book 468: `tafsir-book-468.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.maturidi` tafsir pack (`ar.maturidi.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 468), verbatim:

| Field | Value |
|---|---|
| `name` | تأويلات أهل السنة |
| `short_name` | تفسير الماتريدي |
| `author.full_name` | محمد بن محمد بن محمود، أبو منصور الماتريدي |
| `mohaqeq` | مجدي محمد باسلوم |
| `nasher` | دار الكتب العلمية - بيروت، لبنان |
| `edition` | الأولى |
| `publish_year` | 1426 |
| `parts` | 10 |
| `language` | ar |

Measured in the pinned file before conversion: 6,125 of 6,236
verses have their own entry; 6,065 passages after merging consecutive
verses with identical text; 12.6 million characters of text;
1,814 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Conversion

- Footnotes: editor footnotes (manuscript variants). Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
