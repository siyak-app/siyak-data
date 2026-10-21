# ar.tabari: Jāmiʿ al-Bayān (al-Ṭabarī)

| | |
|---|---|
| Work | Jāmiʿ al-Bayān ʿan Taʾwīl Āy al-Qurʾān (جامع البيان في تأويل آي القرآن) |
| Author | Muḥammad ibn Jarīr al-Ṭabarī (d. 310/923) |
| Edition | مؤسسة الرسالة · الأولى، 1420 ه - 2000 م; editor (محقق): أحمد شاكر |
| Source | Quranpedia.net data dumps, book 4: `tafsir-book-4.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.tabari` tafsir pack (`ar.tabari.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 4), verbatim:

| Field | Value |
|---|---|
| `name` | جامع البيان في تأويل آي القرآن |
| `short_name` | الطبري |
| `author.full_name` | أبو جعفر محمد بن جرير بن يزيد الطبري |
| `mohaqeq` | أحمد شاكر |
| `nasher` | مؤسسة الرسالة |
| `edition` | الأولى، 1420 ه - 2000 م |
| `publish_year` | — |
| `parts` | 24 |
| `language` | ar |

Measured in the pinned file before conversion: 6,236 of 6,236
verses have their own entry; 3,731 passages after merging consecutive
verses with identical text; 21.5 million characters of text;
9,358 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Conversion

- Footnotes: editor footnotes (Aḥmad and Maḥmūd Shākir: sources of poetry, variants, cross-references). Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
