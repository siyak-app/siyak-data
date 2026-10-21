# ar.jalalayn: Tafsīr al-Jalālayn

| | |
|---|---|
| Work | Tafsīr al-Jalālayn (تفسير الجلالين) |
| Author | Jalāl al-Dīn al-Maḥallī and Jalāl al-Dīn al-Suyūṭī (d. 864/1459 and 911/1505) |
| Edition | دار الحديث - القاهرة · الأولى · 1422 - 2001 |
| Source | Quranpedia.net data dumps, book 272: `tafsir-book-272.json.gz` (dump 2026-10-20, file built 2026-08-10) |
| Used in | the `ar.jalalayn` tafsir pack (`ar.jalalayn.sqlite.zst`) |

## Mapping evidence (spec §6.6)

From the dump's book index (`books.json.gz`, entry 272), verbatim:

| Field | Value |
|---|---|
| `name` | تفسير الجلالين |
| `short_name` | تفسير الجلالين |
| `author.full_name` | جلال الدين محمد بن أحمد بن محمد بن إبراهيم المحلي الشافعي |
| `mohaqeq` | — |
| `nasher` | دار الحديث - القاهرة |
| `edition` | الأولى |
| `publish_year` | 1422 - 2001 |
| `parts` | 1 |
| `language` | ar |

Measured in the pinned file before conversion: 6,224 of 6,236
verses have their own entry; 6,224 passages after merging consecutive
verses with identical text; 1.6 million characters of text;
0 editor-footnote blocks.

**Two authors.** The book index names only al-Maḥallī (`author`). Al-Maḥallī wrote the commentary on al-Kahf to al-Nās and on al-Fātiḥa; al-Suyūṭī completed al-Baqara to al-Isrāʾ after his death. The pack credits both.

**Page artifacts.** 692 content items consist only of a page-header residue such as `١ -` or `١٥ -`, and 4,571 items end with one. They are kept verbatim (M1c decision K5), listed in the coverage report and reported to Quranpedia (docs/upstream/quranpedia.md).

Other Quranpedia ids considered:

- 27757: Ḥāshiyat al-Ṣāwī ʿalā Tafsīr al-Jalālayn, a commentary on the work, not the work itself.

## Edition matter and the author's introduction

None found: the dump holds only the author's text (M1c review).

After conversion: 6,224 passages covering 6,226 verses; details in `dist/reports/tafsir-coverage.md`. Source issues reported upstream: `docs/upstream/quranpedia.md`.

## Conversion

- Footnotes: none in this edition. Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
