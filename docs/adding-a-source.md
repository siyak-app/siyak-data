# Adding a source

This guide covers adding a new translation or tafsir source. Read it fully
before opening a pull request. **Licensing comes first:** a source whose
redistribution rights are not confirmed is not added (spec §1, principle 4).

## 1. Propose it

Open a "New source proposal" issue. Fill in the license checklist (§2) as far
as you can, with links. A maintainer adds the `needs-license-check` label until
the checklist is complete and reviewed.

## 2. License checklist

Answer every question with a link or a quotation. "I think so" is not an answer.

| # | Question | Notes |
|---|---|---|
| 1 | **Who holds rights to the text itself?** | Author/translator and their death date; publisher. Classical works are usually public domain, modern translations are not |
| 2 | **Which edition is it?** | Publisher, year, editor (*muḥaqqiq*), print edition. Different editions of the same work may have different rights |
| 3 | **Who made the digitization, and on what terms?** | A public-domain text can still come with terms from whoever typed or scanned it (e.g. Tanzil's non-commercial term for translations) |
| 4 | **Is redistribution allowed?** | As a downloadable file inside an app, not only reading on a website |
| 5 | **Is modification allowed?** | Format conversion (to SQLite, HTML reduced to plain text, paragraph splitting) must be allowed. If only verbatim copies are allowed, the original file may have to ship unchanged next to the derived data (as with QAC) |
| 6 | **Exact attribution wording** | Copy it from the source. Note where it must be shown (app, website, file) and whether a link or version number is required |
| 7 | **Commercial-use terms** | Siyak is free and non-commercial; record any non-commercial clause anyway, it goes into `license_terms` |
| 8 | **Where is the permission recorded?** | The license page or file (archived link), or for written permission a `PERMISSION.md` in the source directory with the full reply |

If any answer is unknown, the source can still be built with `publish = false`
(it never reaches the manifest) while the question is open.

## 3. Add the source directory

```
sources/<group>/<id>/
├─ source.toml   # what to download, pinned sha256, terms, pack metadata
├─ README.md     # origin, edition, terms and how we comply
├─ LICENSE       # the license that applies to the data
└─ NOTICE        # notices that must ship with the data, verbatim
```

`source.toml` (see `sources/translations/en.pickthall/source.toml` for a complete example):

```toml
[source]
id = "en.example"                      # unique; for packs, the pack id
name = "…"
homepage = "https://…"
license = "…"
attribution = "…"
notes = """…"""

[source.terms]                         # required if the source states terms of use
text = """…verbatim…"""
url = "https://…"
accepted_by = "…"                      # only if downloading requires accepting the terms
accepted_on = "YYYY-MM-DD"

[[files]]
name = "en.example.txt"
url = "https://…"
mirror = ""                            # optional: release asset with the exact pinned bytes
version = "…"
sha256 = ""                            # left empty until step 4

[pack]
id = "en.example"
type = "translation"                   # translation | tafsir | morphology | vectors | model | audio
lang = "en"
title = { tr = "…", en = "…" }
author = "…"
version = "1.0.0"
min_app_version = "0.1.0"
license = "…"
attribution = "…"                      # shown on the Packs screen; may be omitted for public domain
publish = false                        # true only after the checklist is approved
bundled = false                        # true only for packs that go into core.db

[pack.license_terms]                   # required when [source.terms] exists
tr = ["…"]
en = ["…"]

[pack.citation]
type = "translation"
author = "…"
title = "…"
publisher = "…"
year = "…"
```

## 4. Pin the files

```sh
uv run siyak-data fetch --pin --source en.example
```

This downloads files without a pinned sha256 into `.cache/` and prints their
hashes. It writes nothing. Open the files, check that they are what you
expect (edition, completeness, encoding), then copy the hashes into
`source.toml` by hand. A maintainer confirms the hashes in review.

If a source can only be downloaded interactively (a form, accepting terms),
do not script around it: download it by hand into `.cache/<source id>/`; the
hash check still applies. Note this in the README.

From then on, `fetch` and `build` fail if a file does not match its pin.

## 5. Build, validate, test

```sh
uv run siyak-data build
uv run siyak-data validate
uv run siyak-data manifest
uv run pytest
```

Add a parser or builder if the format is new, with tests on a tiny fixture
(`tests/fixtures/`). Fixtures of third-party data must respect its terms: whole
lines copied unchanged, with the full notice, or synthetic data.

## 6. Document

- Add a row to `docs/sources.md`.
- Write the source's `README.md`: origin, edition, terms, how each term is met.
- Never change source text. If something looks wrong in the source, report it
  upstream and note it in the README; do not patch it.
