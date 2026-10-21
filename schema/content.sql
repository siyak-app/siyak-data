-- content.db schema, version 1 (PRAGMA user_version = 1).
-- Tables copied exactly from the app specification (siyak/docs/spec/spec.md §5.1–§5.4).
-- Three changes, proposed as spec edits in the M1a report and marked "siyak-data addition":
--   * surahs.bismillah: the basmala Tanzil keeps apart from ayah 1 (sources/tanzil/README.md).
--   * notices: source notices that must ship with the data (e.g. the Tanzil terms).
--   * verses_fts holds normalize(text_clean), not text_clean itself (docs/normalization.md).
-- Vector tables (vec0) are created per pack at install time (M7) and are not part of this file.

-- §5.1 core

CREATE TABLE surahs (
  number          INTEGER PRIMARY KEY,         -- 1..114
  name_ar         TEXT NOT NULL,
  name_tr         TEXT NOT NULL,
  name_en         TEXT NOT NULL,
  revelation_type TEXT NOT NULL CHECK (revelation_type IN ('meccan','medinan')),
  ayah_count      INTEGER NOT NULL,
  bismillah       TEXT                         -- siyak-data addition (proposed §5.1 edit): Uthmani
                                               -- basmala shown above the surah; NULL for 1 and 9
);

CREATE TABLE verses (
  id            INTEGER PRIMARY KEY,           -- global 1..6236
  surah         INTEGER NOT NULL REFERENCES surahs(number),
  ayah          INTEGER NOT NULL,
  juz           INTEGER NOT NULL,
  text_uthmani  TEXT NOT NULL,                 -- display
  text_clean    TEXT NOT NULL,                 -- without diacritics; search
  UNIQUE (surah, ayah)
);

CREATE TABLE packs (
  id            TEXT PRIMARY KEY,              -- e.g. 'en.pickthall'
  type          TEXT NOT NULL CHECK (type IN
                  ('translation','tafsir','morphology','vectors','model')),
  lang          TEXT,
  title         TEXT NOT NULL,
  author        TEXT,
  version       TEXT NOT NULL,                 -- semver
  license       TEXT NOT NULL,
  attribution   TEXT,
  citation_json TEXT,                          -- citation metadata (§11.2)
  meta_json     TEXT,                          -- type-specific fields
  installed_at  TEXT NOT NULL,
  bundled       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE translations (
  pack_id   TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
  verse_id  INTEGER NOT NULL REFERENCES verses(id),
  text      TEXT NOT NULL,
  PRIMARY KEY (pack_id, verse_id)
) WITHOUT ROWID;

-- siyak-data addition (proposed §5.1 edit): notices that must ship with the data,
-- shown in full on About → Sources. One row per notice.
CREATE TABLE notices (
  id      TEXT PRIMARY KEY,                    -- e.g. 'tanzil.text'
  source  TEXT NOT NULL,                       -- source id, e.g. 'tanzil'
  title   TEXT NOT NULL,
  body    TEXT NOT NULL,                       -- verbatim notice text
  url     TEXT
);

-- §5.2 tafsir

CREATE TABLE tafsir (
  id          INTEGER PRIMARY KEY,
  pack_id     TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
  verse_from  INTEGER NOT NULL REFERENCES verses(id),
  verse_to    INTEGER NOT NULL REFERENCES verses(id),
  CHECK (verse_to >= verse_from)
);
CREATE INDEX tafsir_lookup ON tafsir(pack_id, verse_from, verse_to);

CREATE TABLE tafsir_paragraphs (
  tafsir_id  INTEGER NOT NULL REFERENCES tafsir(id) ON DELETE CASCADE,
  idx        INTEGER NOT NULL,                 -- starts at 0
  text       TEXT NOT NULL,
  PRIMARY KEY (tafsir_id, idx)
) WITHOUT ROWID;

-- §5.3 morphology

CREATE TABLE words (
  id         INTEGER PRIMARY KEY,
  verse_id   INTEGER NOT NULL REFERENCES verses(id),
  position   INTEGER NOT NULL,                 -- word order within the verse, from 1
  text_ar    TEXT NOT NULL,                    -- Uthmani
  translit   TEXT,
  gloss_en   TEXT,                             -- if present in the source
  UNIQUE (verse_id, position)
);

CREATE TABLE roots (
  id    INTEGER PRIMARY KEY,
  root  TEXT NOT NULL UNIQUE                   -- in Arabic letters, e.g. 'ق و ل'
);

CREATE TABLE lemmas (
  id       INTEGER PRIMARY KEY,
  lemma    TEXT NOT NULL UNIQUE,
  root_id  INTEGER REFERENCES roots(id)
);

CREATE TABLE word_segments (
  word_id   INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
  idx       INTEGER NOT NULL,
  kind      TEXT NOT NULL CHECK (kind IN ('prefix','stem','suffix')),
  text_ar   TEXT NOT NULL,
  pos       TEXT NOT NULL,                     -- part-of-speech tag
  lemma_id  INTEGER REFERENCES lemmas(id),
  root_id   INTEGER REFERENCES roots(id),
  features  TEXT,                              -- JSON: person, number, gender, mood, case, etc.
  PRIMARY KEY (word_id, idx)
) WITHOUT ROWID;

CREATE INDEX seg_root  ON word_segments(root_id);
CREATE INDEX seg_lemma ON word_segments(lemma_id);

-- §5.4 search indexes
-- siyak-data change (proposed §5.4 edit): verses_fts stores normalize(text_clean)
-- with rowid = verses.id. text_clean itself stays Tanzil's verbatim text; the
-- index is never displayed. The query passes through the same normalize().

CREATE VIRTUAL TABLE verses_fts USING fts5(text_norm);
CREATE VIRTUAL TABLE translations_fts USING fts5(
  text, pack_id UNINDEXED, verse_id UNINDEXED,
  tokenize = 'unicode61 remove_diacritics 2'
);
