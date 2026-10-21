# Pack format

This document specifies the files that `siyak-data` publishes and the Siyak
app installs. It complements the app specification (`siyak/docs/spec/spec.md`
§5 and §6) and is the reference for `pipeline/` and for the app's
`packs/install.rs`.

Format version: **1** (matches `schema_version` in `manifest.json`).

## 1. Files in a data release

A release (tag `data-YYYY.MM.N`) contains:

| Asset | Description |
|---|---|
| `core.db` | The database bundled with the app installer (§3). Not listed in the manifest |
| `<pack id>.sqlite.zst` | One file per SQLite pack, zstd-compressed (§4, §4.3) |
| `<pack id>.tar.zst` | One file per archive pack (§4.4), e.g. `morphology.qac.tar.zst` |
| `manifest.json` | Describes every published pack (§6) |
| `pricing.json` | AI model prices for cost estimates (spec §9.4) |
| `SHA256SUMS` | sha256 of every asset |

## 2. The content schema

`schema/content.sql` is the content.db schema of spec §5.1–§5.4, including:

- `surahs.bismillah`: the basmala Tanzil keeps apart from ayah 1 (NULL for surahs 1 and 9);
- `notices`: notices that must ship with the data, shown on About → Sources;
- `verses_fts` holds `normalize(text_clean)` (docs/normalization.md);
- `content_meta`: the versions of the core data (§3).

Its version is `SCHEMA_VERSION = 1` (`pipeline/schema.py`): the
`PRAGMA user_version` of core.db and the `schema_version` of every pack. The
app's migrations must produce the same structure; the CI job `schema-compat`
checks this against `siyak/src-tauri/migrations/content/`.

## 3. `core.db`

A complete content.db, built from `schema/content.sql`:

| Table | Content |
|---|---|
| `surahs` | 114 rows from Tanzil metadata; `name_tr` from `data/surah-names-tr.csv`; `name_en` is Tanzil's transliterated name (`tname`, e.g. `Al-Faatiha`) |
| `verses` | 6,236 rows; `id` 1..6236 in Mushaf order; `text_uthmani` and `text_clean` are Tanzil's text, verbatim; `juz` from the metadata's juz start points |
| `packs`, `translations` | the bundled translation packs (`bundled = 1`, `installed_at` = build time) |
| `notices` | Tanzil text and metadata notices, and the notice of each bundled pack |
| `verses_fts` | `rowid = verses.id`, `text_norm = normalize(text_clean)` |
| `translations_fts` | one row per bundled translation row |
| `content_meta` | `core_version` and `tanzil_version` (below) |

`PRAGMA user_version` = `SCHEMA_VERSION`, so the app copies core.db to
content.db on first launch and finds it fully migrated.

### `content_meta`

```sql
CREATE TABLE content_meta (
  key    TEXT PRIMARY KEY,
  value  TEXT NOT NULL
);
```

| Key | Value in core.db |
|---|---|
| `core_version` | `CORE_VERSION` in `pipeline/build_core.py`, currently `'1'`: a positive integer written as text, compared as an integer |
| `tanzil_version` | the Tanzil text version, currently `'1.1'`: the version pinned for both text files in `sources/tanzil/source.toml`, which the build checks against the version line of each file's copyright block |

core.db is copied to content.db once, on first launch. `core_version` lets the
app tell that the core.db shipped with a newer app holds different core data
than the user's content.db.

**Bump rule.** `core_version` goes up by one, in the same PR, whenever a rebuild
of core.db would change any row the app reads:

- `verses` (a new Tanzil pin, i.e. a new `tanzil_version`), `surahs` (names,
  basmala, metadata), `notices`;
- the bundled translation packs (their rows, `packs` row or version);
- `verses_fts` (any change to `normalize()`, which also changes the shared
  test vectors);
- the `content_meta` rows themselves.

It does not go up for changes that leave every row the same, such as a new
`built_at` (`packs.installed_at` of bundled packs follows the build time) or
a rebuild that is only byte-different. A schema change raises `SCHEMA_VERSION`
(§2) and, if it also changes rows, `core_version`. `core_version` never goes
down and is never reused.

`validate` fails unless core.db has exactly these two keys, with
`core_version = CORE_VERSION` and `tanzil_version` equal to the pin.

### `notices`

| Column | Meaning |
|---|---|
| `id` | e.g. `tanzil.text.uthmani`, `tanzil.text.simple-clean`, `tanzil.metadata`, or a pack id |
| `source` | the source id from `source.toml` |
| `title` | short English title |
| `body` | the notice text, verbatim where the source provides one (Tanzil's copyright block) |
| `url` | the source's home page |

The app shows every notice in full on About → Sources. Pack notices (from
`sources/**/NOTICE`) are bundled for bundled packs; for downloaded packs the
manifest's `license_terms`/`attribution` are shown, and archive packs carry
their NOTICE inside the archive.

## 4. SQLite packs

Every pack is a SQLite database with:

- exactly one `pack_info` table with exactly one row;
- the tables of its type (§4.1), with the **same names and columns as content.db**
  but without foreign keys to `packs`;
- **nothing else**: no triggers, views or virtual tables, and no tables beyond the
  allow-list of its type. Plain indexes are allowed.

### `pack_info`

```sql
CREATE TABLE pack_info (
  id              TEXT NOT NULL,     -- pack id, e.g. 'en.pickthall'
  type            TEXT NOT NULL,     -- 'translation' | 'tafsir' | 'morphology' | ...
  version         TEXT NOT NULL,     -- the pack's SemVer version (§5)
  schema_version  INTEGER NOT NULL,  -- SCHEMA_VERSION the tables match
  built_at        TEXT NOT NULL,     -- 'YYYY-MM-DDTHH:MM:SSZ'
  source_version  TEXT NOT NULL      -- '<file>@<version>' of each source file, '; '-separated
);
```

The app reads `pack_info` before installing and refuses the file unless
`id` and `type` match the manifest entry and `schema_version` is one it supports.

### 4.1 Tables per pack type

| Type | Tables (columns) |
|---|---|
| `translation` | `translations (pack_id, verse_id, text)`, primary key `(pack_id, verse_id)`, `WITHOUT ROWID` |
| `tafsir` | `tafsir (id, pack_id, verse_from, verse_to)`, `tafsir_paragraphs (tafsir_id, idx, text, part, page)` (spec §5.2), see §4.6 |
| `morphology` | `words (id, verse_id, position, text_ar, translit, gloss_en)`, `roots (id, root)`, `lemmas (id, lemma, root_id)`, `word_segments (word_id, idx, kind, text_ar, pos, lemma_id, root_id, features)` (spec §5.3), inside an archive (§4.4) |

A translation pack has exactly one row per verse (6,236) and no empty text.

### 4.2 Installation (reference: `pipeline/install.py`)

Packs are untrusted input (spec §14.3). After verifying the sha256 of the
downloaded `.sqlite.zst`, the app decompresses it to a temporary `.sqlite`
(§4.3), then:

1. `ATTACH`es the pack;
2. checks `sqlite_master`: only `table` and `index` objects; tables from the
   allow-list of the pack type plus `pack_info`; no `CREATE VIRTUAL TABLE`;
   columns exactly as listed;
3. checks `pack_info` against the manifest entry;
4. in one transaction:
   1. **upserts the `packs` row first** with `INSERT … ON CONFLICT(id) DO UPDATE`;
   2. deletes the pack's existing rows (and its FTS rows);
   3. copies the expected columns with `INSERT … SELECT`, taking `pack_id` from
      the manifest, never from the pack's rows;
   4. refreshes the FTS rows of the pack;
5. `DETACH`es.

The `packs` row must be written first and must never be written with
`INSERT OR REPLACE`. REPLACE deletes the old row, and with foreign keys on,
`ON DELETE CASCADE` then removes the rows that were just copied. Writing the
row last would also violate the foreign key on a first install. The
schema-compat test caught this; spec §6.4 step 6 needs the matching edit.

### 4.3 Compression

Every SQLite pack is published as `<pack id>.sqlite.zst`; `core.db` is not
compressed (the installer compresses it). Decided in the M1a review with these
measurements (zstd 1.5, `python-zstandard` 0.25):

| File | SQLite | zstd-3 | zstd-19 | Decompression |
|---|---|---|---|---|
| Rūḥ al-Maʿānī (largest tafsir, rough conversion) | 55.4 MB | 10.5 MB | 7.1 MB (13 %) | 30 ms |
| Mafātīḥ al-Ghayb (rough conversion) | 55.8 MB | 11.4 MB | 6.3 MB (11 %) | 32 ms |
| al-Jalālayn (rough conversion) | 5.1 MB | 0.9 MB | 0.6 MB (12 %) | 2 ms |
| `en.pickthall` | 1.0 MB | 0.31 MB | 0.26 MB (25 %) | 1 ms |

Rules (implemented in `pipeline/compress.py`):

- a **single zstd frame**, level **19**, single-threaded (deterministic output),
  with the **content size** and a **checksum** in the frame header;
- the manifest's `size` and `sha256` describe the `.zst` file;
  `installed_size` is the decompressed size;
- the app stream-decompresses to a temporary file and **refuses** the pack if
  the frame declares, or the stream produces, more than `installed_size` bytes;
  the temporary file is deleted afterwards (spec §6.4 step 7).

### 4.4 Archive packs (`.tar.zst`)

Used when a pack must ship files besides its database. The archive is a tar
file compressed like SQLite packs (§4.3: one zstd frame, level 19, content
size and checksum in the header). The manifest's `installed_size` is the size
of the tar.

**Tar layout (deterministic):** USTAR format; members in a fixed order; mtime =
build time; uid/gid 0; empty user/group names; mode 0644; regular files only.

**Members per pack type** (`ARCHIVE_LAYOUT` in `pipeline/install.py`). The archive
must hold exactly these names, each once:

| Type | Members |
|---|---|
| `morphology` | `morphology.sqlite`, `qac/COPYING`, `qac/NOTICE`, `qac/quranic-corpus-morphology-0.4.txt` |

**Installation:** after the sha256 check, the app decompresses the tar
(limit `installed_size`) and refuses it unless every member is a regular file
with exactly an expected relative name (no links, no absolute paths, no `..`,
no duplicates). It extracts into a temporary directory, installs the database
as in §4.2, and moves the other files atomically to
`<app_data>/packs/<pack id>/` (for QAC: the original file, NOTICE and license,
which the Sources screen shows in full).

**One morphology pack at a time (v1).** The morphology tables have no `pack_id`.
Installing a morphology pack therefore deletes all rows of `word_segments`,
`words`, `lemmas` and `roots` and the `packs` row of any other morphology pack,
then copies the new rows (in the order roots, lemmas, words, word_segments).

### 4.5 The morphology pack `morphology.qac`

- `words`: one row per Tanzil word (rule A1 of `docs/qac-alignment.md`);
  `id` 1..N in verse order, `position` from 1, `text_ar` is Tanzil's text
  including any attached pause-mark tokens, so `" ".join(text_ar)` of a verse
  equals `verses.text_uthmani`. `translit` and `gloss_en` are NULL (not in QAC).
- `roots.root`: the QAC root in Arabic letters separated by spaces (`ق و ل`).
- `lemmas.lemma`: the QAC lemma in Arabic script; `root_id` its root.
- `word_segments`: one row per line of the QAC file. `idx` is the QAC segment
  number (from 1), so `surah:ayah:position:idx` is the QAC location. `kind` is
  `prefix`/`stem`/`suffix` from the QAC `PREFIX`/`STEM`/`SUFFIX` marker;
  `text_ar` the QAC form in Arabic script; `pos` the QAC part-of-speech tag
  unchanged (e.g. `N`, `V`, `P`, `DET`, `PRON`); `features` see §7.
- Ids of roots and lemmas follow their first occurrence in the QAC file.
- Buckwalter → Arabic uses QAC's extended table (`pipeline/buckwalter.py`),
  with two documented exceptions: a space inside a form is kept (37:130:3,
  إِلْ يَاسِينَ), and QAC's homograph index at the end of a lemma is kept as an
  ASCII digit (`EaAd2` → `عَاد2`; 15 lemmas), because without it two different
  lemmas would share one spelling. The app may render the digit as a
  superscript or hide it, but must keep it for lookups.
- Roots and lemmas are written with QAC's letters as they are; e.g. QAC writes
  the root of ءَامَنَ as `Amn`, giving `ا م ن`. Root search in the app must accept
  hamza spellings (the search normalization does: N5).
- Words merged by alignment rule M (`docs/qac-alignment.md`; four words) hold
  two Tanzil tokens with their space in `text_ar`.

### 4.6 Tafsir packs

Built from the Quranpedia.net dumps (`sources/tafsir/quranpedia/README.md`) by
`pipeline/quranpedia.py` (passages) and `pipeline/tafsir_html.py` (text).

**Tables.**

- `tafsir`: one row per passage. `id` 1..N in verse order; `verse_from`..`verse_to`
  is a range of verse ids within one surah. Passages never overlap, so within a pack
  `verse_from` identifies a passage. A verse outside every passage has no commentary
  in this pack.
- `tafsir_paragraphs`: `idx` from 0. `part` and `page` are the volume and page
  of the printed edition where the paragraph starts. Both are NULL when the source
  gives no page (Quranpedia's page 0 or a missing page); `part` is never set without
  `page`. The app may cite a paragraph as "*title*, part/page".

**Installation.** `tafsir.id` is global in content.db, so the app does not copy
the pack's ids. It inserts the passages, which get new ids, then the paragraphs,
joined on `verse_from` (`_copy_tafsir` in `pipeline/install.py`). It refuses a pack
in which two passages have the same `verse_from`.

**Text: the tafsir HTML subset.** `text` is HTML that uses only:

| Markup | Meaning | From the source |
|---|---|---|
| `<b>…</b>` | emphasis, headings | `strong`, `h3` and the headings written `h٣`/`h٥` |
| `<span class="ayah">…</span>` | a Quran quotation (﴿…﴾) | `span.book-ayah` |
| `<span class="ref">…</span>` | a verse reference, e.g. `[البقرة: ٢]` | `span.surah-ref` |
| `<span class="poem">` … `</span>` | a poem: lines separated by `<br>`, each made of `<span class="hemistich">…</span>` | `table.poem` rows and cells |

Paragraphs end at `br`, `p`, `div`, `hr`, `span.d-block`, headings and poems; a
page break is not a paragraph break. Whitespace runs become one space. Text is
HTML-escaped. Any other source tag fails the build. The app must still sanitize
(the pack is untrusted input) and may style the classes as it likes.

**What the conversion may change, and nothing else** (every letter is accounted
for; see the coverage report):

1. Markup, as above, and whitespace.
2. Editor footnotes (`div.foot-notes`, `a.foot-note`, `span.foot-note`) are left out
   when `[build] footnotes = "drop"` (all v1 packs: M1c decision K2). Footnote
   numbers written as plain text in the running text, e.g. `(١)`, are text and stay.
3. Edition matter listed in `[[build.exclude]]` (editor or publisher
   introductions, studies, manuscript descriptions, indexes, printer colophons)
   is left out. Each rule names the verse(s), volume and pages, optionally the
   line it starts at (`from_text`), and a reason. A rule that matches nothing
   fails the build.
4. The author's own introduction, where the dump attaches it to another verse, is
   moved to the start of 1:1 (`[[build.move_to_start]]`).
5. Quranpedia's copy labels (`نص مكرر لاشتراكه مع الآية N:`, `جزء ذو علاقة من
   تفسير الآية السابقة:`) and the copies that follow them: when the copy's letters
   (compared after the search normalization, so a second digital edition with
   different vocalization still matches) occur in the text stored for the verse
   it points to, the label and copy are not stored again, and the two verses join
   one passage. Unverified copies stay, label included.
6. A piece without a page that repeats the paged text of the same verse, or of a
   verse with no paged text in between, is not stored again (a second digital
   edition), and joins that verse's passage.

**Passages.** Verses that share a section form one passage, unless a verse with
text of its own lies between them (an identical gloss of a refrain does not join
verses). Steps 5 and 6 join verses as described. A verse without text joins the
preceding passage of its surah only if that passage quotes the verse's first
four words (M1c decision K4); other verses stay without commentary.

**Gates** (`pipeline/validate_tafsir.py`): structure and `pack_info`; passage
ranges valid, within one surah, sorted and not overlapping; paragraphs numbered
from 0, not empty, subset markup only, `part`/`page` consistent; the letters of
every passage equal those of the source sections it was built from (read with an
independent tag stripper); coverage at least `[build] min_coverage`; the pack
installs into content.db.

**Reports** (`dist/reports/`): `tafsir-coverage.md` (per pack: passages,
verses covered, gaps, gap merges, copies, edition matter, page artifacts, the
share of verses quoted in their own passage, runs of unquoted verses, and the
letter accounting) and `tafsir-sizes.md`.

## 5. Versions

- **Pack version:** SemVer, in `source.toml` `[pack].version`, bumped by hand
  in the PR that changes the pack's content or its source pin:
  - patch: corrections from the source (new upstream version of the same edition);
  - minor: new derived content (e.g. paragraphs split differently) without a schema change;
  - major: a change that needs a new `schema_version`.
- **`min_app_version`:** `[pack].min_app_version`, default `0.1.0`. Raised when
  a pack needs app features that older versions do not have.
- **`schema_version`:** see §2. The app refuses packs with a `schema_version` it
  does not know.
- **`core_version`:** the version of core.db's content, see §3 (bump rule).
- **Reproducible builds:** `built_at` comes from `SOURCE_DATE_EPOCH` (the tag's
  commit time in releases), rows are inserted in sorted order, and every
  database is `VACUUM`ed. Rebuilding from the same inputs gives a byte-identical
  file, so a changed sha256 always means changed content or metadata.

## 6. `manifest.json`

Generated by `siyak-data manifest` from `manifest.template.json`, the built
files and each `source.toml` `[pack]` table. Shape (spec §6.3):

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-21T00:00:00Z",
  "pricing_url": "https://quran.kemalozyon.com/data/pricing.json",
  "packs": [
    {
      "id": "en.pickthall",
      "type": "translation",
      "lang": "en",
      "title": { "tr": "…", "en": "…" },
      "author": "Marmaduke Pickthall",
      "version": "1.0.0",
      "min_app_version": "0.1.0",
      "size": 256725,
      "installed_size": 1007616,
      "sha256": "…",
      "url": "https://github.com/siyak/siyak-data/releases/download/data-2026.10.0/en.pickthall.sqlite.zst",
      "license": "Public domain",
      "license_terms": { "tr": ["…"], "en": ["…"] },
      "attribution": "…",
      "citation": { "type": "translation", "author": "…", "title": "…", "publisher": "…", "year": "…" }
    }
  ],
  "bundles": []
}
```

- `size` and `sha256` are those of the downloaded file (`.sqlite.zst`);
  `installed_size` is the decompressed size, used for the disk-space display
  and as the decompression limit (§4.3).
- `title` is always a `{ "tr", "en" }` object; optional `description` likewise.
- Optional `meta` (type-specific) and `requires` (dependencies) are added by
  later pack types (vectors, model).
- `url` points at the immutable release asset of the release tag
  (`SIYAK_DATA_TAG`).
- **`publish = false`** packs are built and validated but never written to the
  manifest (e.g. `ar.qurtubi` until permission is granted).
- A source with `[build] requires_permission = true` cannot be published until
  its directory holds `PERMISSION.md` with the rights holder's reply: `manifest`
  refuses it and `validate` fails (spec §6.6, al-Qurtubi).
- **Bundles** come from `manifest.template.json`. Members that are not in the
  release are dropped (with a warning); an empty bundle is omitted. Vector and
  model packs are added to `recommended` in M7.

## 7. Feature keys (morphology)

`word_segments.features` is a JSON object (compact, keys sorted) or NULL. Keys
are stable English names; **values are QAC's codes unchanged**. The app's i18n
labels are keyed by `<key>` and `<key>.<value>` (e.g. `case.GEN`).

| Key | Values (QAC codes) | From QAC token |
|---|---|---|
| `prefix` | `Al+`, `bi+`, `ka+`, `ta+`, `sa+`, `ya+`, `ha+`, `A:INTG+`, `A:EQ+`, `w:CONJ+`, `w:REM+`, `w:CIRC+`, `w:SUP+`, `w:P+`, `w:COM+`, `f:REM+`, `f:CONJ+`, `f:RSLT+`, `f:SUP+`, `f:CAUS+`, `l:P+`, `l:EMPH+`, `l:PRP+`, `l:IMPV+` | the prefix token itself |
| `suffix` | `+VOC`, `+n:EMPH` | the suffix token itself |
| `person` | `1`, `2`, `3` | person/gender/number codes such as `3MS`, `MP`, and `PRON:3MS` |
| `gender` | `M`, `F` | as above |
| `number` | `S`, `D`, `P` | as above |
| `aspect` | `PERF`, `IMPF`, `IMPV` | same |
| `mood` | `IND`, `SUBJ`, `JUS` | `MOOD:…` |
| `voice` | `ACT`, `PASS` | same (when not followed by `PCPL`) |
| `verb_form` | `I` … `XII` | `(I)` … `(XII)` |
| `derivation` | `ACT PCPL`, `PASS PCPL`, `VN` | `ACT\|PCPL`, `PASS\|PCPL`, `VN` |
| `state` | `DEF`, `INDEF` | same |
| `case` | `NOM`, `ACC`, `GEN` | same |
| `special` | e.g. `kaAn`, `<in~` (Buckwalter, as in QAC) | `SP:…` |

`POS:…`, `LEM:…` and `ROOT:…` are not in `features`: the first must equal the
`pos` column, the others become `lemma_id` and `root_id`. A token not covered by
this table fails the build; nothing is dropped silently. The list is final
once the pinned v0.4 file has been parsed completely.
