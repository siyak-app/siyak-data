# Sources

Every text Siyak distributes comes from one of these sources. Each row links to
the source's directory, which holds `source.toml` (URLs, pinned sha256,
terms), `README.md` (origin and edition), `LICENSE` and `NOTICE`.

| Source | Version | License | Attribution | Used in |
|---|---|---|---|---|
| [Tanzil Quran text](../sources/tanzil/) (Uthmani, Simple Clean) | 1.1 | CC BY 3.0 + Tanzil terms: verbatim copies only, no changes; copyright notice must be included | "Quran text: Tanzil Project (https://tanzil.net)", with link | `core.db` |
| [Tanzil Quran metadata](../sources/tanzil/) (`quran-data.xml`) | 1.0 | CC BY (`license="cc-by"`), © 2008-2009 Tanzil.info | Tanzil Project, with link | `core.db` |
| [Pickthall, *The Meaning of the Glorious Koran*](../sources/translations/en.pickthall/) (Tanzil digitization) | 2010-09-04 | Translation public domain; Tanzil digitization for non-commercial use | "Digitized text: Tanzil Project (tanzil.net)" | `core.db` (bundled), `en.pickthall` |
| Turkish surah names ([`data/surah-names-tr.csv`](../data/surah-names-tr.csv)) | — | Project data, `MIT OR Apache-2.0` | — | `core.db` (`surahs.name_tr`) |

Coming in later stages: Quranic Arabic Corpus v0.4 (M1b, GNU GPL, verbatim
only, research/non-commercial), classical tafsirs from Quranpedia.net dumps
(M1c), al-Qurtubi from QUL (M1c, unpublished until permission).

## Restrictive terms at a glance

| Pack | Term | Where users see it |
|---|---|---|
| `core.db` | Tanzil text may not be changed; notice must be shown | About → Sources (`notices` table) |
| `en.pickthall` | Tanzil digitization: non-commercial use | Packs screen (`license_terms`), About → Sources |
