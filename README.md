# siyak-data

[Türkçe](README.tr.md)

The data pipeline of [Siyak](https://github.com/siyak-app/siyak), a free,
open-source Quran research tool. It builds the content the app ships and
downloads:

- **`core.db`**: bundled with the installer: the Tanzil Quran text (Uthmani and
  Simple Clean), surah metadata, and the bundled translations;
- **packs**: translations, 16 classical tafsirs (from the Quranpedia.net dumps)
  and the Quranic Arabic Corpus morphology, downloaded from the app's Packs
  screen and published zstd-compressed (`<id>.sqlite.zst`, archives as
  `<id>.tar.zst`);
- **`manifest.json`** and **`pricing.json`**: describe the packs and AI model prices.

Code: `MIT OR Apache-2.0`. **Data keeps its own licenses**: see
[docs/sources.md](docs/sources.md) and `sources/*/LICENSE`.

## Quick start

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run siyak-data fetch      # download pinned sources into .cache/ (sha256-checked)
uv run siyak-data build      # build dist/core.db and dist/<pack>.sqlite.zst
uv run siyak-data validate   # run the validation gates
uv run siyak-data manifest   # write dist/manifest.json and dist/pricing.json
```

Without network access, build the committed test fixtures instead:

```sh
uv run siyak-data build --profile fixtures
uv run siyak-data validate --profile fixtures
```

`uv run siyak-data check-updates` compares upstream sources with their pinned versions.

Semantic search packs (an embedding model and its verse vectors) need the optional ML
libraries and are built by a separate command:

```sh
uv sync --group embed
uv run siyak-data build-embeddings   # model packs, then vector packs (ONNX Runtime)
uv run siyak-data eval-embeddings    # score models and verse texts on data/eval/semantic.toml
```

To try packs in a debug build of the app before publishing them,
`uv run siyak-data manifest --unpublished` lists every built pack, then run the app with
`SIYAK_PACK_SOURCE=../siyak-data/dist`.

## How it works

- **Sources are pinned.** Each source is described by `sources/<…>/source.toml`:
  download URL, version, expected sha256, license, attribution. Downloaded files
  live in `.cache/` (not in git); `fetch` and `build` fail if a file's hash
  differs from its pin. No third-party data is committed, except tiny verbatim
  excerpts used as test fixtures (`tests/fixtures/README.md`).
- **Source text is never changed.** Conversions change format only.
- **Validation gates** (114 surahs, 6,236 verses, contiguous ayahs, complete
  translations, no marks in the clean text, installability…) stop a release
  with a message that names the exact verse or table.
- **Reproducible builds:** with the same inputs and `SOURCE_DATE_EPOCH`, every
  file is byte-identical.

## Documentation

| Document | Contents |
|---|---|
| [docs/pack-format.md](docs/pack-format.md) | Pack and manifest format, install rules, versions |
| [docs/normalization.md](docs/normalization.md) | Arabic search normalization rules (shared with the app) |
| [docs/sources.md](docs/sources.md) | Every source with version, license and attribution |
| [docs/adding-a-source.md](docs/adding-a-source.md) | How to add a translation or tafsir, with the license checklist |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup and workflow |

## Releases

Pushing a tag `data-YYYY.MM.N` runs `.github/workflows/data-release.yml`:
fetch → build → validate → `SHA256SUMS` → manifest and pricing → GitHub release.
The app reads the manifest from `https://quran.kemalozyon.com/data/manifest.json`,
with `https://github.com/siyak-app/siyak-data/releases/latest/download/manifest.json`
as fallback.
