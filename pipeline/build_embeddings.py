"""Model packs and vector packs (docs/pack-format.md §4.5, §4.6; app spec §6.1, §7.4).

``uv run --group embed siyak-data build-embeddings`` builds, for every ``[pack]`` of type
``model`` and ``vectors``:

- ``<model id>.tar.zst``: ``model.sqlite`` (only ``pack_info``), ``model/model.onnx``
  (the pinned upstream export, optionally quantized to int8), ``model/tokenizer.json``
  (with the pad token set) and ``model/LICENSE``;
- ``<vectors id>.sqlite`` / ``.sqlite.zst``: ``pack_info`` and ``vectors(verse_id,
  embedding)``, one little-endian float32 vector per verse.

An ``api`` vector pack has no model pack: its verses are embedded with the provider's API
(:mod:`pipeline.api_embedding`), with the maintainers' key from the environment.

Verse vectors are computed by :class:`OnnxEncoder` from the files of the built model pack,
which mirrors the app's ``embed/onnx.rs`` (prefixes, truncation, padding, inputs by name,
pooling, normalization), so the app's query vectors and these verse vectors share one space.
"""

from __future__ import annotations

import json
import math
import shutil
import sqlite3
import tempfile
import tomllib
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pipeline.api_embedding import ApiSpec, api_spec, encoder_for, passage_cache
from pipeline.archive import build_archive, extract_archive
from pipeline.build_translation import require_pack, source_version
from pipeline.compress import MAX_PACK_SIZE, compress_pack
from pipeline.embedding import VARIANTS, VERSE_COUNT, ModelSpec, verse_texts
from pipeline.errors import PipelineError
from pipeline.fetch import verify_cached
from pipeline.install import ARCHIVE_LAYOUT
from pipeline.paths import data_dir
from pipeline.schema import SCHEMA_VERSION, PackInfo, finalize, new_database, write_pack_info
from pipeline.sources import Source

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    Matrix = npt.NDArray[np.float32]

DB_MEMBER = "model.sqlite"
MODEL_MEMBER = "model/model.onnx"
TOKENIZER_MEMBER = "model/tokenizer.json"
LICENSE_MEMBER = "model/LICENSE"
#: Texts run through the model at once, as in the app.
BATCH = 16
#: A unit vector's length may differ from 1 by this much (the app checks the same).
NORM_TOLERANCE = 1e-3

VECTORS_DDL = """
CREATE TABLE vectors (
  verse_id   INTEGER PRIMARY KEY,
  embedding  BLOB NOT NULL
)
"""


def model_spec(source: Source) -> ModelSpec:
    """The model pack's metadata as a :class:`ModelSpec`; ``meta`` must be complete."""
    pack = require_pack(source)
    meta = pack.meta
    where = f"{source.path} [pack.meta]"
    model = str(meta.get("embedding_model", ""))
    if not model.startswith("local/"):
        raise PipelineError(f"{where}: embedding_model must start with local/")
    pooling = str(meta.get("pooling", "mean"))
    if pooling not in ("mean", "cls", "last"):
        raise PipelineError(f"{where}: pooling must be mean, cls or last")
    if meta.get("normalized") is not True:
        raise PipelineError(f"{where}: normalized must be true")
    return ModelSpec(
        key=model.removeprefix("local/"),
        repo=str(source.extra.get("repo", "")),
        dim=int(meta["dim"]),
        pooling=pooling,
        query_prefix=str(meta.get("query_prefix", "")),
        passage_prefix=str(meta.get("passage_prefix", "")),
        license=pack.license,
        max_tokens=int(meta.get("max_tokens", 512)),
    )


class OnnxEncoder:
    """Runs a model pack's files the way the app's ``OnnxEmbedder`` does."""

    def __init__(self, model_dir: Path, spec: ModelSpec) -> None:
        import onnxruntime as ort  # noqa: PLC0415 (optional dependency)
        from tokenizers import Tokenizer  # noqa: PLC0415

        self.spec = spec
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tokenizer.enable_truncation(spec.max_tokens)
        padding = self.tokenizer.padding
        if padding is None:
            raise PipelineError(f"{model_dir}/tokenizer.json has no padding (pad token)")
        self.tokenizer.enable_padding(
            pad_id=padding["pad_id"], pad_token=padding["pad_token"], direction="right"
        )
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(model_dir / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.inputs = {i.name for i in self.session.get_inputs()}
        if not {"input_ids", "attention_mask"} <= self.inputs:
            raise PipelineError("model.onnx needs input_ids and attention_mask inputs")

    def encode(self, texts: Sequence[str], prefix: str) -> Matrix:
        """Unit vectors of ``prefix + text``, one row per text."""
        import numpy as np  # noqa: PLC0415

        rows = [
            self._batch([prefix + t for t in texts[i : i + BATCH]])
            for i in range(0, len(texts), BATCH)
        ]
        return np.concatenate(rows) if rows else np.zeros((0, self.spec.dim), np.float32)

    def _batch(self, texts: list[str]) -> Matrix:
        import numpy as np  # noqa: PLC0415

        encodings = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encodings], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feed: dict[str, Any] = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        if "position_ids" in self.inputs:
            feed["position_ids"] = np.maximum(np.cumsum(mask, axis=1) - 1, 0) * mask
        out = np.asarray(self.session.run(None, feed)[0], dtype=np.float32)
        dim = self.spec.dim
        if out.ndim == 2 and out.shape == (len(texts), dim):
            vectors = out
        elif out.ndim == 3 and out.shape[0] == len(texts) and out.shape[2] == dim:
            vectors = pool(out, mask, self.spec.pooling)
        else:
            raise PipelineError(f"model output {out.shape}, expected [{len(texts)}, ..., {dim}]")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        result: Matrix = (vectors / np.where(norms > 0, norms, 1)).astype(np.float32)
        return result


def pool(hidden: Matrix, mask: Any, pooling: str) -> Matrix:
    """Pool ``[batch, tokens, dim]`` token vectors as the app does."""
    import numpy as np  # noqa: PLC0415

    if pooling == "cls":
        first: Matrix = hidden[:, 0, :]
        return first
    if pooling == "last":
        last = np.maximum(mask.sum(axis=1) - 1, 0)
        # Right padding: the last used token is at (number of used tokens - 1).
        picked: Matrix = hidden[np.arange(hidden.shape[0]), last, :]
        return picked
    weights = mask[:, :, None].astype(np.float32)
    mean: Matrix = (hidden * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1.0)
    return mean


def prepare_tokenizer(src: Path, dest: Path) -> None:
    """Copy ``tokenizer.json`` with padding set to the model's own pad token.

    The app keeps the pad token from the file and pads each batch to its longest text;
    truncation is set by the app from ``max_tokens``.
    """
    from tokenizers import Tokenizer  # noqa: PLC0415

    tokenizer = Tokenizer.from_file(str(src))
    pad_token = next(
        (t for t in ("<pad>", "[PAD]", "<|endoftext|>") if tokenizer.token_to_id(t) is not None),
        None,
    )
    if pad_token is None:
        raise PipelineError(f"{src}: no pad token")
    pad_id = tokenizer.token_to_id(pad_token)
    tokenizer.enable_padding(pad_id=pad_id, pad_token=pad_token, direction="right")
    tokenizer.no_truncation()
    tokenizer.save(str(dest), pretty=False)


def quantize(src: Path, dest: Path) -> None:
    """Dynamic int8 quantization of the weights (activations stay float)."""
    from onnxruntime.quantization import QuantType, quantize_dynamic  # noqa: PLC0415

    quantize_dynamic(str(src), str(dest), weight_type=QuantType.QInt8)


def build_model_pack(source: Source, out_dir: Path, *, built_at: str, mtime: int) -> list[Path]:
    """Build ``<id>.sqlite`` (pack_info only) and ``<id>.tar.zst``; return both paths."""
    pack = require_pack(source)
    if pack.type != "model":
        raise PipelineError(f"{source.path}: pack type is '{pack.type}', not 'model'")
    model_spec(source)
    # Every file: an export may keep its weights next to model.onnx (external data).
    for f in source.files:
        verify_cached(source, f.name)
    model = verify_cached(source, "model.onnx")
    tokenizer = verify_cached(source, "tokenizer.json")
    license_file = verify_cached(source, "LICENSE")
    with tempfile.TemporaryDirectory(prefix="siyak-model-") as tmp:
        work = Path(tmp)
        prepared_model = work / "model.onnx"
        method = source.extra.get("quantize")
        if method == "int8":
            quantize(model, prepared_model)
        elif method is None:
            shutil.copyfile(model, prepared_model)
        else:
            raise PipelineError(f"{source.path}: [build] quantize must be 'int8' or absent")
        prepared_tokenizer = work / "tokenizer.json"
        prepare_tokenizer(tokenizer, prepared_tokenizer)
        info = PackInfo(
            pack.id, pack.type, pack.version, SCHEMA_VERSION, built_at, source_version(source)
        )
        db = out_dir / f"{pack.id}.sqlite"
        with closing(new_database(db)) as conn:
            write_pack_info(conn, info)
            conn.commit()
            finalize(conn)
        members = [
            (DB_MEMBER, db),
            (LICENSE_MEMBER, license_file),
            (MODEL_MEMBER, prepared_model),
            (TOKENIZER_MEMBER, prepared_tokenizer),
        ]
        return [db, build_archive(out_dir, pack.id, members, mtime)]


def unpack_model(archive: Path, dest: Path) -> Path:
    """Extract a built model pack; return the directory holding its model files."""
    _db, members = ARCHIVE_LAYOUT["model"]
    files = extract_archive(archive, dest, expected=set(members), max_size=MAX_PACK_SIZE)
    return files[MODEL_MEMBER].parent


def vector_settings(source: Source, models: dict[str, Source]) -> tuple[Source, str]:
    """The model pack source and the verse text of a local vector pack."""
    pack = require_pack(source)
    where = f"{source.path}"
    meta = pack.meta
    model_id = str(meta.get("model_pack", ""))
    if meta.get("backend") != "local" or model_id not in models:
        raise PipelineError(f"{where}: needs backend = 'local' and a model_pack built here")
    if pack.requires != (model_id,):
        raise PipelineError(f"{where}: requires must be exactly ['{model_id}']")
    model_pack = require_pack(models[model_id]).meta
    for key in ("embedding_model", "dim"):
        if meta.get(key) != model_pack.get(key):
            raise PipelineError(f"{where}: {key} differs from {model_id}")
    text = str(source.extra.get("text", ""))
    if text not in VARIANTS:
        raise PipelineError(f"{where}: [build] text must be one of {', '.join(VARIANTS)}")
    return models[model_id], text


def api_vector_settings(source: Source) -> tuple[ApiSpec, str]:
    """The API settings and the verse text of an ``api`` vector pack."""
    pack = require_pack(source)
    where = f"{source.path}"
    spec = api_spec(pack.meta, where)
    if pack.requires:
        raise PipelineError(f"{where}: an api vector pack requires no other pack")
    text = str(source.extra.get("text", ""))
    if text not in VARIANTS:
        raise PipelineError(f"{where}: [build] text must be one of {', '.join(VARIANTS)}")
    return spec, text


def build_vector_pack(
    source: Source, models: dict[str, Source], out_dir: Path, *, built_at: str
) -> list[Path]:
    """Build ``<id>.sqlite`` and ``<id>.sqlite.zst``: from the built model pack (``local``)
    or with the provider's API (``api``, key from the environment)."""
    pack = require_pack(source)
    if pack.type != "vectors":
        raise PipelineError(f"{source.path}: pack type is '{pack.type}', not 'vectors'")
    if pack.meta.get("backend") == "api":
        api, text = api_vector_settings(source)
        vectors = encoder_for(api).encode(
            verse_texts(text), "passage", cache=passage_cache(api, text)
        )
        check_matrix(vectors, api.dim, str(source.path))
        inputs = [f"{api.embedding_model} ({api.dim})", f"text {text}"]
    else:
        model_source, text = vector_settings(source, models)
        spec = model_spec(model_source)
        archive = out_dir / f"{require_pack(model_source).id}.tar.zst"
        if not archive.exists():
            raise PipelineError(f"{archive}: build the model pack first")
        with tempfile.TemporaryDirectory(prefix="siyak-vectors-") as tmp:
            encoder = OnnxEncoder(unpack_model(archive, Path(tmp)), spec)
            vectors = encoder.encode(verse_texts(text), spec.passage_prefix)
        check_matrix(vectors, spec.dim, str(source.path))
        model_pack = require_pack(model_source)
        inputs = [f"{model_pack.id}@{model_pack.version}", f"text {text}"]
    info = PackInfo(pack.id, pack.type, pack.version, SCHEMA_VERSION, built_at, "; ".join(inputs))
    db = out_dir / f"{pack.id}.sqlite"
    with closing(new_database(db)) as conn:
        write_pack_info(conn, info)
        conn.execute(VECTORS_DDL)
        conn.executemany(
            "INSERT INTO vectors (verse_id, embedding) VALUES (?, ?)",
            ((i + 1, row.astype("<f4").tobytes()) for i, row in enumerate(vectors)),
        )
        conn.commit()
        finalize(conn)
    return [db, compress_pack(db)]


def check_matrix(vectors: Matrix, dim: int, where: str) -> None:
    """One finite unit vector of ``dim`` values per verse."""
    import numpy as np  # noqa: PLC0415

    if vectors.shape != (VERSE_COUNT, dim):
        raise PipelineError(
            f"{where}: vectors are {vectors.shape}, expected ({VERSE_COUNT}, {dim})"
        )
    if not np.isfinite(vectors).all():
        raise PipelineError(f"{where}: vectors contain NaN or infinity")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.all(np.abs(norms - 1) <= NORM_TOLERANCE):
        raise PipelineError(f"{where}: vectors are not unit length")


def check_vector_pack(path: Path, dim: int) -> list[str]:
    """Problems of a built vector pack: verse coverage, sizes, finite unit vectors."""
    import numpy as np  # noqa: PLC0415

    problems: list[str] = []
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute("SELECT verse_id, embedding FROM vectors ORDER BY verse_id").fetchall()
    ids = [r[0] for r in rows]
    if ids != list(range(1, VERSE_COUNT + 1)):
        problems.append(f"{path.name}: verse ids are not exactly 1..{VERSE_COUNT}")
    for verse_id, blob in rows:
        if not isinstance(blob, bytes) or len(blob) != dim * 4:
            problems.append(f"{path.name}: verse {verse_id} has a vector of the wrong size")
            break
        vector = np.frombuffer(blob, dtype="<f4")
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(vector).all() or not math.isclose(norm, 1, abs_tol=NORM_TOLERANCE):
            problems.append(f"{path.name}: verse {verse_id} is not a finite unit vector")
            break
    return problems


def reference_texts() -> list[str]:
    """The first three queries of each language of the evaluation set."""
    raw = tomllib.loads((data_dir() / "eval" / "semantic.toml").read_text(encoding="utf-8"))
    texts: list[str] = []
    for lang in ("tr", "en", "ar"):
        texts += [str(q["text"]) for q in raw["query"] if q["lang"] == lang][:3]
    return texts


def write_reference(source: Source, out_dir: Path, dest: Path) -> Path:
    """Write a test directory for the app: the model files and reference vectors.

    ``SIYAK_TEST_MODEL_DIR=<dest> cargo test -- --ignored matches_the_pipeline``.
    """
    spec = model_spec(source)
    pack = require_pack(source)
    archive = out_dir / f"{pack.id}.tar.zst"
    if dest.exists():
        shutil.rmtree(dest)
    with tempfile.TemporaryDirectory(prefix="siyak-reference-") as tmp:
        shutil.copytree(unpack_model(archive, Path(tmp)), dest / "model")
    model_dir = dest / "model"
    texts = reference_texts()
    vectors = OnnxEncoder(model_dir, spec).encode(texts, spec.query_prefix)
    reference = {
        "spec": pack.meta,
        "texts": texts,
        "kind": "query",
        "vectors": vectors.tolist(),
    }
    out = dest / "reference.json"
    out.write_text(json.dumps(reference, ensure_ascii=False), encoding="utf-8")
    return out
