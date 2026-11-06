"""Evaluation set, model and vector pack rules (pipeline/embedding*.py, eval_embeddings.py).

The ML libraries are an optional dependency group; tests that need numpy are skipped
without it.
"""

import sqlite3
import struct
from contextlib import closing
from pathlib import Path

import pytest

from pipeline.build_embeddings import (
    VERSE_COUNT,
    check_vector_pack,
    model_spec,
    pool,
    vector_settings,
)
from pipeline.errors import PipelineError
from pipeline.eval_embeddings import Item, excluded, load_items, parse_refs, score
from pipeline.install import install_pack
from pipeline.manifest import PACK_FILE
from pipeline.paths import data_dir
from pipeline.schema import (
    SCHEMA_VERSION,
    PackInfo,
    apply_content_schema,
    new_database,
    write_pack_info,
)
from pipeline.sources import Source, load_source
from pipeline.tanzil import parse_metadata

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def refs() -> list[tuple[int, int]]:
    """(surah, ayah) of all 6,236 verses, from the full Tanzil metadata."""
    metadata = parse_metadata(FIXTURES / "cache" / "tanzil" / "quran-data.xml")
    return [(s.number, a) for s in metadata.surahs for a in range(1, s.ayah_count + 1)]


def test_the_evaluation_set_names_existing_verses(refs: list[tuple[int, int]]) -> None:
    items = load_items(data_dir() / "eval" / "semantic.toml", refs)
    groups = {g: sum(1 for i in items if i.group == g) for g in ("tr", "en", "ar", "related")}
    assert all(count >= 20 for count in groups.values()), groups
    assert all(item.relevant for item in items)
    ids = {ref: i + 1 for i, ref in enumerate(refs)}
    assert ids[(2, 255)] == 262
    first = items[0]
    assert first.relevant == frozenset(ids[(2, a)] for a in (183, 184, 185, 187))


def test_refs_and_ranges(refs: list[tuple[int, int]]) -> None:
    ids = {ref: i + 1 for i, ref in enumerate(refs)}
    assert parse_refs(["1:1", "1:6-7", "114:6"], ids, "t") == [1, 6, 7, 6236]
    for bad in ["1:8", "115:1", "2", "2:x", "2:3-x"]:
        with pytest.raises(PipelineError, match="not a verse"):
            parse_refs([bad], ids, "t")


def test_cross_references_leave_out_the_neighbourhood(
    refs: list[tuple[int, int]], tmp_path: Path
) -> None:
    near = excluded(262, refs)  # 2:255
    assert near == set(range(257, 268))
    assert excluded(1, refs) == set(range(1, 7))  # al-Fatiha has 7 verses
    path = tmp_path / "eval.toml"
    path.write_text('[[related]]\nverse = "2:255"\nrelevant = ["2:258"]\n', encoding="utf-8")
    with pytest.raises(PipelineError, match="within 5"):
        load_items(path, refs)
    path.write_text('[[query]]\nlang = "de"\ntext = "x"\nrelevant = ["1:1"]\n', encoding="utf-8")
    with pytest.raises(PipelineError, match="lang"):
        load_items(path, refs)


def test_scores() -> None:
    relevant = frozenset({5, 9})
    assert score([5, 1, 9], relevant) == (1.0, 1.0, 1.0)
    assert score([1, 2, 9], relevant) == (1.0, 0.5, 1 / 3)
    assert score(list(range(10, 30)), relevant) == (0.0, 0.0, 0.0)
    # Recall counts at most 10 relevant verses.
    many = frozenset(range(1, 21))
    assert score(list(range(1, 11)), many)[1] == 1.0
    assert Item("tr", "x", relevant).source is None


MODEL = """
[source]
id = "model.test"
name = "test"
homepage = "https://example.org"
license = "MIT"
attribution = "test"

[[files]]
name = "model.onnx"
url = "https://example.org/model.onnx"
version = "1"
sha256 = "00"

[pack]
id = "model.test"
type = "model"
lang = "mul"
title = { tr = "t", en = "t" }
author = "a"
version = "1.0.0"
license = "MIT"
publish = false

[pack.meta]
embedding_model = "local/test"
dim = 4
normalized = true
query_prefix = "query: "
pooling = "cls"
"""

VECTORS = """
[source]
id = "vectors.test"
name = "test"
homepage = "https://example.org"
license = "x"
attribution = "x"

[build]
text = "ar+tr+en"

[pack]
id = "vectors.test"
type = "vectors"
lang = "mul"
title = { tr = "t", en = "t" }
author = "a"
version = "1.0.0"
license = "x"
requires = ["model.test"]
publish = false

[pack.meta]
embedding_model = "local/test"
dim = 4
normalized = true
source_text = "x"
backend = "local"
model_pack = "model.test"
"""


def source(tmp_path: Path, name: str, text: str) -> Source:
    path = tmp_path / name / "source.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return load_source(path)


def test_model_and_vector_pack_settings(tmp_path: Path) -> None:
    model = source(tmp_path, "model", MODEL)
    spec = model_spec(model)
    assert (spec.key, spec.dim, spec.pooling, spec.query_prefix) == ("test", 4, "cls", "query: ")
    assert spec.passage_prefix == ""
    assert spec.max_tokens == 512
    vectors = source(tmp_path, "vectors", VECTORS)
    assert vectors.pack is not None
    assert vectors.pack.requires == ("model.test",)
    assert vector_settings(vectors, {"model.test": model}) == (model, "ar+tr+en")
    assert PACK_FILE["vectors"] == "{id}.sqlite.zst"
    assert PACK_FILE["model"] == "{id}.tar.zst"

    for old, new, message in [
        ('requires = ["model.test"]', "requires = []", "requires"),
        (
            "dim = 4\nnormalized = true\nsource_text",
            "dim = 8\nnormalized = true\nsource_text",
            "dim",
        ),
        ('text = "ar+tr+en"', 'text = "fr"', "text"),
        ('backend = "local"', 'backend = "api"', "backend"),
    ]:
        broken = source(tmp_path, "broken", VECTORS.replace(old, new))
        with pytest.raises(PipelineError, match=message):
            vector_settings(broken, {"model.test": model})
    for old, new in [
        ('pooling = "cls"', 'pooling = "max"'),
        ('embedding_model = "local/test"', 'embedding_model = "openai/test"'),
        ("normalized = true", "normalized = false"),
    ]:
        with pytest.raises(PipelineError):
            model_spec(source(tmp_path, "broken-model", MODEL.replace(old, new)))


def test_a_vector_pack_installs(tmp_path: Path) -> None:
    content = tmp_path / "content.db"
    with closing(new_database(content)) as conn:
        apply_content_schema(conn)
        conn.execute(
            "INSERT INTO surahs (number, name_ar, name_tr, name_en, revelation_type, ayah_count) "
            "VALUES (1, 'x', 'x', 'x', 'meccan', 2)"
        )
        conn.executemany(
            "INSERT INTO verses (id, surah, ayah, text_uthmani, text_clean, juz) "
            "VALUES (?, 1, ?, 'x', 'x', 1)",
            [(1, 1), (2, 2)],
        )
        conn.commit()
    pack = tmp_path / "vectors.test.sqlite"
    with closing(new_database(pack)) as conn:
        write_pack_info(
            conn, PackInfo("vectors.test", "vectors", "1.0.0", SCHEMA_VERSION, "now", "x")
        )
        conn.execute("CREATE TABLE vectors (verse_id INTEGER PRIMARY KEY, embedding BLOB)")
        for verse in (1, 2):
            conn.execute("INSERT INTO vectors VALUES (?, ?)", (verse, struct.pack("<2f", 0.6, 0.8)))
        conn.commit()
    row = {
        "id": "vectors.test",
        "type": "vectors",
        "lang": "mul",
        "title": "t",
        "version": "1.0.0",
        "license": "x",
        "installed_at": "now",
    }
    with closing(sqlite3.connect(content)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        install_pack(conn, pack, row)
        install_pack(conn, pack, row)  # an update replaces the rows
        rows = conn.execute("SELECT pack_id, verse_id FROM verse_vectors ORDER BY 2").fetchall()
        assert rows == [("vectors.test", 1), ("vectors.test", 2)]
        with conn:
            conn.execute("DELETE FROM packs WHERE id = 'vectors.test'")
        assert conn.execute("SELECT count(*) FROM verse_vectors").fetchone() == (0,)


def test_vector_pack_gate(tmp_path: Path) -> None:
    pytest.importorskip("numpy")

    path = tmp_path / "v.sqlite"

    def write(blobs: dict[int, bytes]) -> list[str]:
        path.unlink(missing_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE vectors (verse_id INTEGER PRIMARY KEY, embedding BLOB)")
            conn.executemany("INSERT INTO vectors VALUES (?, ?)", blobs.items())
            conn.commit()
        return check_vector_pack(path, 2)

    unit = struct.pack("<2f", 0.6, 0.8)
    good = dict.fromkeys(range(1, VERSE_COUNT + 1), unit)
    assert write(good) == []
    assert "1..6236" in write({**good, VERSE_COUNT + 1: unit})[0]
    assert "wrong size" in write({**good, 3: struct.pack("<3f", 1, 0, 0)})[0]
    assert "unit vector" in write({**good, 3: struct.pack("<2f", 1, 1)})[0]
    assert "unit vector" in write({**good, 3: struct.pack("<2f", float("nan"), 1)})[0]


def test_pooling_matches_the_app() -> None:
    np = pytest.importorskip("numpy")

    # The same numbers as the app's pools_token_vectors test (embed/onnx.rs).
    hidden = np.arange(1, 13, dtype=np.float32).reshape(2, 3, 2)
    mask = np.array([[1, 1, 1], [1, 1, 0]])
    assert pool(hidden, mask, "mean").tolist() == [[3.0, 4.0], [8.0, 9.0]]
    assert pool(hidden, mask, "cls").tolist() == [[1.0, 2.0], [7.0, 8.0]]
    assert pool(hidden, mask, "last").tolist() == [[5.0, 6.0], [9.0, 10.0]]
