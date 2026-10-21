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

## Conversion

- Footnotes: editor footnotes (mostly verse references). Not included (`footnotes = "drop"`, M1c decision K2);
  the count is in the coverage report.
- Everything else follows `docs/pack-format.md` §4.6: the HTML is reduced to
  the tafsir subset, the text itself is never changed.

Terms of use and how they are met: `../quranpedia/README.md`.
