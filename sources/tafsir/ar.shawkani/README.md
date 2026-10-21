# ar.shawkani: Fatḥ al-Qadīr (al-Shawkānī)

| | |
|---|---|
| Work | Fatḥ al-Qadīr al-Jāmiʿ bayna Fannay al-Riwāya wa-l-Dirāya (فتح القدير الجامع بين فني الرواية والدراية من علم التفسير) |
| Author | Muḥammad ibn ʿAlī al-Shawkānī (d. 1250/1834) |
| Edition | دار ابن كثير، دار الكلم الطيب - دمشق، بيروت · الأولى · 1414 |
| Source | Quranpedia.net data dumps, book 343: `tafsir-book-343.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.shawkani` tafsir pack (`ar.shawkani.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 343), verbatim:

| Field | Value |
|---|---|
| `name` | فتح القدير الجامع بين فني الرواية والدراية من علم التفسير |
| `short_name` | فتح القدير |
| `author.full_name` | محمد بن علي بن محمد بن عبد الله الشوكاني اليمني |
| `mohaqeq` | — |
| `nasher` | دار ابن كثير، دار الكلم الطيب - دمشق، بيروت |
| `edition` | الأولى |
| `publish_year` | 1414 |
| `parts` | 1 |
| `language` | ar |

Measured in the pinned file before conversion: 6,214 of 6,236
verses have their own entry; 5,765 passages after merging consecutive
verses with identical text; 30.3 million characters of text;
1,802 editor-footnote blocks.


Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`. "introduction"
marks the author's own introduction, stored as a separate `kind = "introduction"`
passage at 1:1:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| left out | 114:1-114:6 | 1 | 5–12 | Editor's introduction (التعريف بالمؤلف والكتاب) |
| left out | any | 1 | 629–632 | Index of volume 1 (فهرس الجزء الأول) |
| left out | 4:176 | 2 | 4–4 | Editor's note on the Quran text (تنبيه) |
| left out | any | 4 | 665–667 | Index of volume 4 (فهرس الموضوعات) |
| left out | any | 5 | 647–650 | Index of volume 5 (فهرس الموضوعات) |
| left out | any | 6 | all | Volume 6: the editor's indexes |
| introduction | 114:1-114:6 | 1 | 13–19 | Author's introduction (مقدّمة المؤلف) |

After conversion: 1,374 passages covering 6,236 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Passages follow the edition's group headings ("[سورة … : الآيات a الى b]",
  `passage_headings = true`, M1c decision): Quranpedia copies the reports
  section of one group to the first verse of the next, which would otherwise join
  neighbouring groups (e.g. 26:69–157). The coverage report lists the number of
  headings and of passages that changed.
- Footnotes: editor footnotes (mostly verse references). Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
