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

`schema/content.sql` is the content.db schema (spec §5.1–§5.4) plus three
additions proposed as spec edits:

- `surahs.bismillah`: the basmala Tanzil keeps apart from ayah 1 (NULL for surahs 1 and 9);
- `notices`: notices that must ship with the data, shown on About → Sources;
- `verses_fts` holds `normalize(text_clean)` (docs/normalization.md).

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

`PRAGMA user_version` = `SCHEMA_VERSION`, so the app copies core.db to
content.db on first launch and finds it fully migrated.

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
| `tafsir` | `tafsir`, `tafsir_paragraphs` (spec §5.2): added in M1c |
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
- Buckwalter → Arabic uses QAC's extended table (`pipeline/buckwalter.py`).

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
