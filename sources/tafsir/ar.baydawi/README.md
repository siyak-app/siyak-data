# ar.baydawi: Anwār al-Tanzīl (al-Bayḍāwī)

| | |
|---|---|
| Work | Anwār al-Tanzīl wa-Asrār al-Taʾwīl (أنوار التنزيل وأسرار التأويل) |
| Author | ʿAbd Allāh ibn ʿUmar al-Bayḍāwī (d. 685/1286 (approx.)) |
| Edition | دار إحياء التراث العربي - بيروت · الأولى - 1418 ه; editor (محقق): محمد عبد الرحمن المرعشلي |
| Source | Quranpedia.net data dumps, book 319: `tafsir-book-319.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.baydawi` tafsir pack (`ar.baydawi.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 319), verbatim:

| Field | Value |
|---|---|
| `name` | أنوار التنزيل وأسرار التأويل |
| `short_name` | تفسير البيضاوي |
| `author.full_name` | ناصر الدين أبو سعيد عبد الله بن عمر بن محمد الشيرازي البيضاوي |
| `mohaqeq` | محمد عبد الرحمن المرعشلي |
| `nasher` | دار إحياء التراث العربي - بيروت |
| `edition` | الأولى - 1418 ه |
| `publish_year` | — |
| `parts` | 1 |
| `language` | ar |

Measured in the pinned file before conversion: 6,236 of 6,236
verses have their own entry; 1,188 passages after merging consecutive
verses with identical text; 3.8 million characters of text;
8 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`. "introduction"
marks the author's own introduction, stored as a separate `kind = "introduction"`
passage at 1:1:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| left out | 114:1-114:6 | 1 | 5–20 | Editor's introduction (مقدمة التحقيق) |
| left out | 114:1-114:6 | 5 | 353–356 | Table of contents of volume 5 (محتوى الجزء الخامس) |
| introduction | 114:1-114:6 | 1 | 23–23 | Author's preface |

After conversion: 1,188 passages covering 6,236 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: editor footnotes. Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
