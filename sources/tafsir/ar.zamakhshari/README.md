# ar.zamakhshari: al-Kashshāf (al-Zamakhsharī)

| | |
|---|---|
| Work | al-Kashshāf ʿan Ḥaqāʾiq al-Tanzīl (الكشاف عن حقائق التنزيل وعيون الأقاويل في وجوه التأويل) |
| Author | Maḥmūd ibn ʿUmar al-Zamakhsharī (d. 538/1144) |
| Edition | دار الكتاب العربي - بيروت · الثالثة - 1407 ه |
| Source | Quranpedia.net data dumps, book 346: `tafsir-book-346.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.zamakhshari` tafsir pack (`ar.zamakhshari.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 346), verbatim:

| Field | Value |
|---|---|
| `name` | الكشاف عن حقائق التنزيل وعيون الأقاويل في وجوه التأويل |
| `short_name` | الكشاف أو تفسير الزمخشري |
| `author.full_name` | محمود بن عمر بن محمد بن أحمد الخوارزمي الزمخشريّ، جار الله، أبو القاسم |
| `mohaqeq` | — |
| `nasher` | دار الكتاب العربي - بيروت |
| `edition` | الثالثة - 1407 ه |
| `publish_year` | — |
| `parts` | 4 |
| `language` | ar |

Measured in the pinned file before conversion: 6,233 of 6,236
verses have their own entry; 2,042 passages after merging consecutive
verses with identical text; 6.7 million characters of text;
2,579 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| moved to 1:1 | 114:6 | المقدمة | 1–4 | Author's introduction (مقدمة التفسير) |

After conversion: 2,020 passages covering 6,234 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: footnotes of the printed edition, mostly Ibn al-Munayyir's al-Intiṣāf (d. 683/1284, classical) plus notes by the edition's corrector; dropped in v1 with the others (K2), a candidate for `footnotes = "keep"` later. Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
