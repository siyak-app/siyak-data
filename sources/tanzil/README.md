# Tanzil: Quran text and metadata

| | |
|---|---|
| Publisher | Tanzil Project, <https://tanzil.net> |
| Texts | Uthmani and Simple Clean, **version 1.1** (February 2021) |
| Metadata | `quran-data.xml`, version 1.0 |
| License | Creative Commons Attribution 3.0, with Tanzil's terms of use (see `LICENSE`, `NOTICE`) |
| Used in | `core.db`: `verses.text_uthmani`, `verses.text_clean`, `surahs`, `verses.juz`, `notices` |

## Edition and download options

The files are downloaded from Tanzil's download form
(<https://tanzil.net/download/>) in **XML format**. The exact URLs are in
`source.toml`.

- **Uthmani** with Tanzil's default options: pause marks, sajdah signs and tatweel below
  superscript alefs on; rub-el-hizb signs off. Pause marks are written as separate
  tokens between words (e.g. `رَيْبَ ۛ فِيهِ`).
- **Simple Clean** without options. With `marks=true`, Tanzil adds pause marks
  even to the "clean" text, which would break the "no marks in `text_clean`" gate.

**Why XML:** Tanzil's plain-text export prefixes the basmala to ayah 1 of every
surah except 1 and 9 (`2|1|بِسْمِ ٱللَّهِ … الٓمٓ`). The XML export keeps it in a
separate `bismillah` attribute, so `verses` holds the ayah text alone and the
basmala goes to `surahs.bismillah`. Both exports carry the same text: for every
verse, XML `bismillah + " " + text` equals the plain-text line (checked for all
6,236 verses of both texts on 2026-10-21). In the Uthmani text the basmala of
surahs 95 and 97 differs from the others (`بِّسْمِ`, with shadda), so it is stored
per surah, not as a constant.

## Terms of use and how we comply

| Term (from the files' copyright block) | Compliance |
|---|---|
| Verbatim copies only; "CHANGING IT IS NOT ALLOWED" | Text is stored exactly as downloaded. Normalized text exists only in the search index `verses_fts` and is never displayed. `text_clean` is Tanzil's Simple Clean text, not derived by our normalizer |
| Source (Tanzil Project) clearly indicated, with a link to tanzil.net | `notices` rows; "About → Sources" in the app; `docs/sources.md` |
| Copyright notice included in all copies and derived files | The copyright blocks ship verbatim in `core.db` (`notices`) and in `NOTICE` |

The download form requires accepting the terms ("I agree with Terms of Use").
The project maintainer accepted them on 2026-10-21 (`source.toml`, `[source.terms]`).

## Pinning and the mirror

Tanzil's copyright line contains the current year (`Copyright (C) 2007-2026`),
so the files' sha256 changes every January even if the text does not. To keep
builds reproducible, the exact pinned files are also published as assets of
the siyak-data release `sources-tanzil-1.1` (verbatim copies, which the terms
allow); `fetch` tries that mirror first and falls back to tanzil.net. Run
`uv run siyak-data check-updates --source tanzil` to see whether tanzil.net
differs from the pin and which lines changed.

To create the mirror once (maintainer, after the hashes are confirmed and the
files are in `.cache/tanzil/`):

```sh
gh release create sources-tanzil-1.1 --repo siyak/siyak-data \
  --title "Source mirror: Tanzil 1.1" \
  --notes "Verbatim copies of the pinned Tanzil files (see sources/tanzil/README.md)." \
  .cache/tanzil/quran-uthmani.xml .cache/tanzil/quran-simple-clean.xml .cache/tanzil/quran-data.xml
```
