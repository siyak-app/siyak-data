# Sources

Every text Siyak distributes comes from one of these sources. Each row links to
the source's directory, which holds `source.toml` (URLs, pinned sha256,
terms), `README.md` (origin and edition), `LICENSE` and `NOTICE`.

| Source | Version | License | Attribution | Used in |
|---|---|---|---|---|
| [Tanzil Quran text](../sources/tanzil/) (Uthmani, Simple Clean) | 1.1 | CC BY 3.0 + Tanzil terms: verbatim copies only, no changes; copyright notice must be included | "Quran text: Tanzil Project (https://tanzil.net)", with link | `core.db` |
| [Tanzil Quran metadata](../sources/tanzil/) (`quran-data.xml`) | 1.0 | CC BY (`license="cc-by"`), © 2008-2009 Tanzil.info | Tanzil Project, with link | `core.db` |
| [Pickthall, *The Meaning of the Glorious Koran*](../sources/translations/en.pickthall/) (Tanzil digitization) | 2010-09-04 | Translation public domain; Tanzil digitization for non-commercial use | "Digitized text: Tanzil Project (tanzil.net)" | `core.db` (bundled), `en.pickthall` |
| [Quranic Arabic Corpus morphology](../sources/morphology/qac/) (Kais Dukes, University of Leeds) | 0.4 (2011) | GNU GPL (version not stated; GPL-3.0 text included) + QAC terms: verbatim copies only, no changes; non-commercial use (FAQ) | "Source: Quranic Arabic Corpus" with a link to https://corpus.quran.com | `morphology.qac` |
| [Tanzil translations](../sources/translations/) (15 English: `en.ahmedali`, `en.ahmedraza`, `en.arberry`, `en.daryabadi`, `en.hilali`, `en.itani`, `en.maududi`, `en.mubarakpuri`, `en.qarai`, `en.qaribullah`, `en.sahih`, `en.sarwar`, `en.shakir`, `en.wahiduddin`, `en.yusufali`; 9 Turkish: `tr.ates`, `tr.bulac`, `tr.diyanet`, `tr.golpinarli`, `tr.ozturk`, `tr.vakfi`, `tr.yazir`, `tr.yildirim`, `tr.yuksel`) | per file, see each `source.toml` | Tanzil terms: non-commercial use, link back to the list when using more than three, the list may not be redistributed on another website without permission. Rights in each translation not verified | "Digitized text: Tanzil Project (https://tanzil.net/trans/)" | the pack of the same id; published by the maintainer's decision on 2026-11-03 |
| Turkish surah names ([`data/surah-names-tr.csv`](../data/surah-names-tr.csv)) | — | Project data, `MIT OR Apache-2.0` | — | `core.db` (`surahs.name_tr`) |

| [Quranpedia.net tafsir dumps](../sources/tafsir/quranpedia/) (16 classical tafsirs, one directory each: `sources/tafsir/ar.*`) | dump 2026-10-20 | Classical works: public domain. Digitization: Quranpedia.net Data License 2026-10-19: republishing as a dataset requires credit with link and the dump version; keep copies current via the changes API | "Source: Quranpedia.net · dump 2026-10-20 (https://quranpedia.net)" | `ar.tabari`, `ar.ibn-kathir`, `ar.razi`, `ar.zamakhshari`, `ar.baydawi`, `ar.jalalayn`, `ar.baghawi`, `ar.nasafi`, `ar.maturidi`, `ar.abussuud`, `ar.bursevi`, `ar.alusi`, `ar.suyuti-durr`, `ar.ibn-atiyya`, `ar.abu-hayyan`, `ar.shawkani` |

| [al-Qurṭubī, *al-Jāmiʿ li-Aḥkām al-Qurʾān*](../sources/tafsir/ar.qurtubi/) (Quranic Universal Library, Tarteel, resource #23) | file 2025-05-26 | Classical work: public domain. QUL digitization: no license or origin stated; permission requested | "Source: Quranic Universal Library (Tarteel)", with link | `ar.qurtubi`, **not published** until `PERMISSION.md` records Tarteel's reply |

## Restrictive terms at a glance

| Pack | Term | Where users see it |
|---|---|---|
| `core.db` | Tanzil text may not be changed; notice must be shown | About → Sources (`notices` table) |
| `en.pickthall` | Tanzil digitization: non-commercial use | Packs screen (`license_terms`), About → Sources |
| `en.*`, `tr.*` from Tanzil | Non-commercial use; link to https://tanzil.net/trans/; the list may not be redistributed on another website without permission | Packs screen (`attribution`, `license_terms`), About → Sources |
| `ar.*` tafsirs | Credit Quranpedia.net with link and dump version; text is the printed edition's; editor footnotes and edition matter left out; packs updated when Quranpedia corrects the text | Packs screen (`attribution`, `license_terms`), tafsir panel, About → Sources |
| `morphology.qac` | Original file only verbatim; tags never corrected (errata: `docs/qac-errata.md`); source + link wherever shown; non-commercial | Packs screen (`license_terms`), word card, Word panel, concordance, exports, About → Sources (`qac/NOTICE` in full) |
