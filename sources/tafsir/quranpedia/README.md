# Quranpedia.net tafsir dumps

Sixteen of the seventeen v1 tafsir packs (spec §6.6) are built from the data
dumps of Quranpedia.net (الموسوعة القرآنية). This file describes what is shared
by all of them; each pack has its own directory (`../ar.<name>/`) with its
`source.toml`, the mapping evidence for its book id, and its notes.

| | |
|---|---|
| Publisher | Quranpedia.net, <https://quranpedia.net>, contact quranpedia.help@gmail.com |
| Dumps | <https://quranpedia.net/dumps/manifest.json>: one `tafsir-book-<id>.json.gz` per book, with sha256 and `built_at` |
| Pinned dump | version `2026-10-20` (manifest `generated_at` 2026-10-20T03:32:35Z); the pinned tafsir files were built 2026-08-10 |
| License | Quranpedia.net Data License, version 2026-10-19, verbatim in `LICENSE.md` |
| Changes API | `https://quranpedia.net/api/v1/changes?since=<version>` |

## File format

A dump file is gzip-compressed JSON:

```
{ "license": {…}, "book": {id, name, short_name, parts, publish_year, edition,
  nasher, author{…}, mohaqeq, …}, "schema": "/v1/ayah/{surah}/{ayah}/book/<id>",
  "ayahs": [ { "surah": 2, "ayah": 153,
               "content": [ { "text": "<html>", "part": "1", "page": 31,
                              "image": "<page scan URL>", "ayahs": "160" } ] } ] }
```

- One entry per verse that has commentary. Verses explained together carry
  the same text under each of them.
- `content` items are **pieces of printed pages**, not paragraphs: a passage
  that runs over a page break is split into two items.
- `part`/`page` locate the item in the printed edition (used for citations,
  `tafsir_paragraphs.part`/`page`).
- `ayahs` is meant to list the global verse ids an item covers, but some books
  hold the verse number within the surah there instead. The pipeline groups
  verses by identical text (spec §5.2) and reports disagreements with `ayahs`;
  it never relies on that field.
- The text is HTML: `span.book-ayah` for Quran quotations, `table.poem` for
  verse, `h3` headings, `div.foot-notes` and `a.foot-note` for the editor's
  footnotes, `span.surah-ref` for references, `strong`, `br`, `p`.

## Terms of use and how we comply (spec §6.6)

| Term (LICENSE.md, verbatim in substance) | Compliance |
|---|---|
| Classical works are shared heritage; the digitization, structuring, verification, *ḍabṭ* and metadata are Quranpedia's work | Packs carry only pre-modern works (author died in the 19th century or earlier). Quranpedia is credited for the digitization |
| Translations and contemporary works belong to their authors and publishers | No contemporary works. Editor footnotes (*taḥqīq* notes by modern editors) are dropped from every v1 pack (`[build] footnotes = "drop"`; counts in the coverage report) |
| Republishing as a downloadable dataset requires crediting Quranpedia.net with a link and stating the dump version | Every pack's `attribution`: "Source: Quranpedia.net · dump 2026-10-20 (https://quranpedia.net)", shown on the Packs screen, in the tafsir panel and on About → Sources; also in `docs/sources.md` |
| Keep copies current via the changes API; outdated text is the distributor's responsibility | `siyak-data check-updates` asks the changes API for every pinned book; a changed book is re-pinned and its pack published with a new version |
| Provided as-is; verification is the user's duty | The app notes "The text is the source's edition; please report errors"; errors are forwarded to Quranpedia (`docs/upstream/quranpedia.md`) |

The text of the work is never changed. Conversion is limited to what
`docs/pack-format.md` §4.6 lists: HTML reduced to the tafsir subset, paragraph
splitting, merging verses with identical text, verified gap merging, and
dropping editor footnotes.

## Mirror

The license allows republishing with credit and the dump version, and dump
files on quranpedia.net are rebuilt in place. `fetch` therefore takes the
pinned bytes from a siyak-data release:

```sh
gh release create sources-quranpedia-2026-10-20 --repo siyak-app/siyak-data --latest=false \
  --title "Source mirror: Quranpedia.net tafsir dumps 2026-10-20" \
  --notes "Verbatim copies. Source: Quranpedia.net (https://quranpedia.net), dump 2026-10-20. See sources/tafsir/quranpedia/README.md." \
  .cache/ar.*/tafsir-book-*.json.gz
```
