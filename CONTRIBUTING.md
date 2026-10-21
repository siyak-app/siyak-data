# Contributing to siyak-data

[Türkçe](CONTRIBUTING.tr.md)

Thank you for helping. You can contribute without writing code: proposing a
source (with license research), reviewing Turkish surah names, or reporting a
data error are all valuable. Use the issue forms.

## Setup

```sh
uv sync                                    # Python ≥ 3.12, dev tools included
uv run siyak-data build --profile fixtures # works offline
uv run pytest
```

For a full build: `uv run siyak-data fetch && uv run siyak-data build && uv run siyak-data validate`.

## Checks (CI runs the same)

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy            # --strict, for pipeline/
uv run pytest
```

Never open a PR with failing checks.

## Rules

- **English only** in code, comments, commit messages, PRs and docs
  (except `*.tr.md` files).
- **Never alter source content.** Conversions change format only. If a source
  has an error, report it upstream; do not patch it.
- **No third-party data in git**, except tiny verbatim test fixtures that the
  source's terms allow (see `tests/fixtures/README.md`).
- **Pins are reviewed.** A new or changed sha256 in `source.toml` needs a
  reviewer who checked the file.
- **Normalization is a contract** with the app: rule changes follow
  `docs/normalization.md` → "Changing the rules".
- **New sources** follow [docs/adding-a-source.md](docs/adding-a-source.md),
  including the license checklist.

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `build:`, `ci:`, `refactor:`, `chore:`.
- One logical change per PR; describe what changed, why, and how you tested it.
- Data changes: state which packs change and bump their `[pack].version`
  (`docs/pack-format.md` §5).

## Project layout

| Path | Contents |
|---|---|
| `pipeline/` | the Python package behind `siyak-data` |
| `schema/content.sql` | the content database schema packs must satisfy |
| `sources/` | one directory per source: `source.toml`, `README.md`, `LICENSE`, `NOTICE` |
| `data/` | small hand-written data (Turkish surah names, pricing) |
| `tests/` | tests, shared normalization vectors, fixtures |
| `docs/` | format and process documentation |
