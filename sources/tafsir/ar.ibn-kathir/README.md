# ar.ibn-kathir: Tafsīr al-Qurʾān al-ʿAẓīm (Ibn Kathīr)

| | |
|---|---|
| Work | Tafsīr al-Qurʾān al-ʿAẓīm (تفسير القرآن العظيم) |
| Author | Ismāʿīl ibn ʿUmar ibn Kathīr (d. 774/1373) |
| Edition | دار طيبة للنشر والتوزيع · الثانية · 1420; editor (محقق): سامي سلامة |
| Source | Quranpedia.net data dumps, book 136: `tafsir-book-136.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.ibn-kathir` tafsir pack (`ar.ibn-kathir.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 136), verbatim:

| Field | Value |
|---|---|
| `name` | تفسير القرآن العظيم |
| `short_name` | تفسير ابن كثير |
| `author.full_name` | أبو الفداء إسماعيل بن عمر بن كثير القرشي البصري ثم الدمشقي |
| `mohaqeq` | سامي سلامة |
| `nasher` | دار طيبة للنشر والتوزيع |
| `edition` | الثانية |
| `publish_year` | 1420 |
| `parts` | 8 |
| `language` | ar |

Measured in the pinned file before conversion: 6,054 of 6,236
verses have their own entry; 5,931 passages after merging consecutive
verses with identical text; 20.5 million characters of text;
7,230 editor-footnote blocks.


Other Quranpedia ids considered:

- 331: same work, Dār al-Kutub al-ʿIlmiyya 1419, ed. Muḥammad Ḥusayn Shams al-Dīn (6,228 verses with an entry). Not chosen: the Dār Ṭayba edition is the standard critical edition.
- 521, 1575: abridgements of the work by al-Ṣābūnī and al-Rifāʿī (contemporary), not the work itself.

## Edition matter and the author's introduction

Found in the M1c review (page-order check and index detection over the whole
dump, then each run read); applied by the rules in `source.toml`. "introduction"
marks the author's own introduction, stored as a separate `kind = "introduction"`
passage at 1:1:

| Rule | Verse(s) | Volume | Pages | What it is |
|---|---|---|---|---|
| left out | 114:6 | 0 | all | Editor's introduction, study, manuscripts and plates (volume 0) |
| introduction | 114:6 | 1 | 5–100 | Author's introduction (مقدمة ابن كثير) |

After conversion: 2,671 passages covering 6,231 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: editor footnotes (Sāmī Salāma: hadith references, manuscript variants). Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
