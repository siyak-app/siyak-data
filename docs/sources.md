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
| Turkish surah names ([`data/surah-names-tr.csv`](../data/surah-names-tr.csv)) | — | Project data, `MIT OR Apache-2.0` | — | `core.db` (`surahs.name_tr`) |

Coming in M1c: classical tafsirs from Quranpedia.net dumps, al-Qurtubi from
QUL (unpublished until permission).

## Restrictive terms at a glance

| Pack | Term | Where users see it |
|---|---|---|
| `core.db` | Tanzil text may not be changed; notice must be shown | About → Sources (`notices` table) |
| `en.pickthall` | Tanzil digitization: non-commercial use | Packs screen (`license_terms`), About → Sources |
| `morphology.qac` | Original file only verbatim; tags never corrected (errata: `docs/qac-errata.md`); source + link wherever shown; non-commercial | Packs screen (`license_terms`), word card, Word panel, concordance, exports, About → Sources (`qac/NOTICE` in full) |
