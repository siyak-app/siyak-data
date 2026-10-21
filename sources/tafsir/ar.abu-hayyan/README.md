# ar.abu-hayyan: al-Baḥr al-Muḥīṭ (Abū Ḥayyān)

| | |
|---|---|
| Work | al-Baḥr al-Muḥīṭ fī al-Tafsīr (البحر المحيط في التفسير) |
| Author | Abū Ḥayyān al-Andalusī (d. 745/1344) |
| Edition | دار الفكر - بيروت · 1420; editor (محقق): صدقي محمد جميل |
| Source | Quranpedia.net data dumps, book 322: `tafsir-book-322.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.abu-hayyan` tafsir pack (`ar.abu-hayyan.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 322), verbatim:

| Field | Value |
|---|---|
| `name` | البحر المحيط في التفسير |
| `short_name` | — |
| `author.full_name` | أبو حيان أثير الدين محمد بن يوسف بن علي بن يوسف بن حيان الأندلسي |
| `mohaqeq` | صدقي محمد جميل |
| `nasher` | دار الفكر - بيروت |
| `edition` | — |
| `publish_year` | 1420 |
| `parts` | 1 |
| `language` | ar |

Measured in the pinned file before conversion: 6,236 of 6,236
verses have their own entry; 340 passages after merging consecutive
verses with identical text; 18.7 million characters of text;
3,421 editor-footnote blocks.


Other Quranpedia ids considered:

- 27762: al-Nahr al-Mādd min al-Baḥr al-Muḥīṭ, the author's abridgement, a different work.

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`. "introduction"
marks the author's own introduction, stored as a separate `kind = "introduction"`
passage at 1:1:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| left out | 114:1-114:6 | 1 | 3–7 | Publisher's introduction (مقدمة الناشر) and editorial method |
| introduction | 114:1-114:6 | 1 | 9–26 | Author's preface (خطبة الكتاب) |

After conversion: 340 passages covering 6,236 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: editor footnotes (mostly verse references). Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
