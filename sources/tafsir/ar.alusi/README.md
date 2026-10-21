# ar.alusi: Rūḥ al-Maʿānī (al-Ālūsī)

| | |
|---|---|
| Work | Rūḥ al-Maʿānī fī Tafsīr al-Qurʾān al-ʿAẓīm wa-l-Sabʿ al-Mathānī (روح المعاني) |
| Author | Shihāb al-Dīn Maḥmūd al-Ālūsī (d. 1270/1854) |
| Edition | دار الكتب العلمية - بيروت · الأولى · 1415; editor (محقق): علي عبد البارى عطية |
| Source | Quranpedia.net data dumps, book 301: `tafsir-book-301.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.alusi` tafsir pack (`ar.alusi.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 301), verbatim:

| Field | Value |
|---|---|
| `name` | روح المعاني |
| `short_name` | تفسير الألوسي |
| `author.full_name` | أبو المعالي محمود شكري بن عبد الله بن محمد بن أبي الثناء الألوسي |
| `mohaqeq` | علي عبد البارى عطية |
| `nasher` | دار الكتب العلمية - بيروت |
| `edition` | الأولى |
| `publish_year` | 1415 |
| `parts` | 1 |
| `language` | ar |

Measured in the pinned file before conversion: 6,236 of 6,236
verses have their own entry; 549 passages after merging consecutive
verses with identical text; 20.2 million characters of text;
740 editor-footnote blocks.

**Author in the Quranpedia metadata is wrong.** `books.json` names أبو المعالي محمود شكري بن عبد الله بن محمد بن أبي الثناء الألوسي, i.e. Maḥmūd Shukrī al-Ālūsī (d. 1342/1924), the author's grandson. *Rūḥ al-Maʿānī* is by Shihāb al-Dīn Abū al-Thanāʾ Maḥmūd ibn ʿAbd Allāh al-Ālūsī (d. 1270/1854); the edition (Dār al-Kutub al-ʿIlmiyya 1415, ed. ʿAlī ʿAbd al-Bārī ʿAṭiyya) is of his work. The pack uses the correct author; the error is reported to Quranpedia (docs/upstream/quranpedia.md).

Other Quranpedia ids considered:

- None: no other Quranpedia tafsir dump carries this work.

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| moved to 1:1 | 114:1 | 1 | 3–35 | Author's preface (خطبة المفسر) and introduction |

After conversion: 488 passages covering 6,236 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: editor footnotes (including notes on the author's own marginalia). Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
