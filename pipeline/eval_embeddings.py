"""Compare embedding models and verse texts on the evaluation set (app spec §18, 1–3).

``uv run --group embed siyak-data eval-embeddings`` embeds every verse with each model and
text variant (cached under ``.cache/embeddings/``), ranks all 6,236 verses for each query of
``data/eval/semantic.toml`` and reports, per language and for cross-references:

- hit@10: a relevant verse is among the first 10;
- recall@10: the share of relevant verses among the first 10 (at most 10 can be found);
- MRR@10: 1 / rank of the first relevant verse (0 if it is not among the first 10).

Models run with sentence-transformers (PyTorch) here; ``build_vectors`` checks that the
exported ONNX model, which the app runs, gives the same vectors.
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pipeline.api_embedding import RateLimit, encoder_for
from pipeline.embedding import VARIANTS, ModelSpec, get_model, verse_refs, verse_texts
from pipeline.errors import PipelineError
from pipeline.paths import cache_dir, data_dir
from pipeline.sources import Source

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    Matrix = npt.NDArray[np.float32]

K = 10
# Verses this close to a cross-reference's starting verse (same surah) are not ranked.
NEIGHBOURHOOD = 5


@dataclass(frozen=True)
class Item:
    """One query or cross-reference of the evaluation set."""

    group: str  # 'tr', 'en', 'ar' or 'related'
    text: str  # the query, or the starting verse as 'surah:ayah'
    relevant: frozenset[int]  # verse ids
    source: int | None = None  # the starting verse id of a cross-reference


def parse_refs(refs: Sequence[str], ids: dict[tuple[int, int], int], where: str) -> list[int]:
    """Turn ``surah:ayah`` and ``surah:a-b`` strings into verse ids."""
    out: list[int] = []
    for ref in refs:
        try:
            surah, ayahs = ref.split(":")
            first, _, last = ayahs.partition("-")
            span = range(int(first), int(last or first) + 1)
            out.extend(ids[(int(surah), a)] for a in span)
        except (ValueError, KeyError):
            raise PipelineError(f"{where}: not a verse: {ref!r}") from None
    return out


def load_items(path: Path, refs: list[tuple[int, int]]) -> list[Item]:
    """Read the evaluation set; every verse must exist."""
    ids = {ref: i + 1 for i, ref in enumerate(refs)}
    raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    items: list[Item] = []
    for n, query in enumerate(raw.get("query", []), start=1):
        where = f"{path.name}: query {n}"
        if query.get("lang") not in ("tr", "en", "ar"):
            raise PipelineError(f"{where}: lang must be tr, en or ar")
        relevant = frozenset(parse_refs(query["relevant"], ids, where))
        items.append(Item(query["lang"], query["text"], relevant))
    for n, related in enumerate(raw.get("related", []), start=1):
        where = f"{path.name}: related {n}"
        [source] = parse_refs([related["verse"]], ids, where)
        relevant = frozenset(parse_refs(related["relevant"], ids, where))
        if relevant & excluded(source, refs):
            raise PipelineError(f"{where}: lists a verse within {NEIGHBOURHOOD} of the start")
        items.append(Item("related", related["verse"], relevant, source))
    if not items:
        raise PipelineError(f"{path}: no queries")
    return items


def excluded(source: int, refs: list[tuple[int, int]]) -> set[int]:
    """The starting verse and its neighbours in the same surah."""
    surah, ayah = refs[source - 1]
    return {i + 1 for i, (s, a) in enumerate(refs) if s == surah and abs(a - ayah) <= NEIGHBOURHOOD}


def score(ranked: Sequence[int], relevant: frozenset[int]) -> tuple[float, float, float]:
    """(hit@K, recall@K, MRR@K) of one ranking."""
    top = list(ranked[:K])
    found = [i for i, verse in enumerate(top) if verse in relevant]
    hit = 1.0 if found else 0.0
    recall = len(found) / min(len(relevant), K)
    mrr = 1.0 / (found[0] + 1) if found else 0.0
    return hit, recall, mrr


def evaluate(
    items: list[Item], passages: Matrix, queries: Matrix, refs: list[tuple[int, int]]
) -> dict[str, tuple[float, float, float, int]]:
    """Mean (hit, recall, MRR, count) per group and over all items.

    ``passages`` holds one unit vector per verse (row = id - 1); ``queries`` one per query
    item, in order (cross-references use their verse's passage vector).
    """
    import numpy as np  # noqa: PLC0415 (optional dependency)

    totals: dict[str, list[tuple[float, float, float]]] = {}
    q = 0
    for item in items:
        if item.source is None:
            vector = queries[q]
            q += 1
            skip: set[int] = set()
        else:
            vector = passages[item.source - 1]
            skip = excluded(item.source, refs)
        scores = passages @ vector
        order = np.argsort(-scores, kind="stable")
        ranked = [int(i) + 1 for i in order[: K + len(skip)] if int(i) + 1 not in skip]
        result = score(ranked, item.relevant)
        totals.setdefault(item.group, []).append(result)
        totals.setdefault("all", []).append(result)
    return {
        group: (
            sum(r[0] for r in rows) / len(rows),
            sum(r[1] for r in rows) / len(rows),
            sum(r[2] for r in rows) / len(rows),
            len(rows),
        )
        for group, rows in totals.items()
    }


class TorchEncoder:
    """A model loaded with sentence-transformers (the reference implementation)."""

    def __init__(self, spec: ModelSpec) -> None:
        import torch  # noqa: PLC0415
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.spec = spec
        self.model = SentenceTransformer(spec.repo, device=device)
        self.model.max_seq_length = spec.max_tokens

    def encode(self, texts: list[str], prefix: str, batch_size: int = 16) -> Matrix:
        """Unit vectors of ``prefix + text``, one row per text."""
        import numpy as np  # noqa: PLC0415

        vectors = self.model.encode(
            [prefix + t for t in texts],
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


def passage_vectors(encoder: TorchEncoder, variant: str) -> Matrix:
    """Verse vectors of one model and text, cached in ``.cache/embeddings/``."""
    import numpy as np  # noqa: PLC0415

    path = cache_dir() / "embeddings" / encoder.spec.key / f"{variant}.npy"
    if path.exists():
        cached: Matrix = np.load(path)
        return cached
    vectors = encoder.encode(verse_texts(variant), encoder.spec.passage_prefix)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, vectors)
    return vectors


def run_eval(models: list[str], variants: list[str], out: Path) -> str:
    """Evaluate every model with every text; write a Markdown report to ``out`` and return it."""
    for variant in variants:
        if variant not in VARIANTS:
            raise PipelineError(f"unknown text {variant!r}; known: {', '.join(VARIANTS)}")
    refs = verse_refs()
    items = load_items(data_dir() / "eval" / "semantic.toml", refs)
    groups = ["tr", "en", "ar", "related", "all"]
    counts = {g: sum(1 for i in items if g in ("all", i.group)) for g in groups}
    lines = [
        "# Embedding evaluation",
        "",
        f"`data/eval/semantic.toml`: {len(items)} items "
        + ", ".join(f"{g} {counts[g]}" for g in groups[:-1])
        + f". Cells: hit@{K} / recall@{K} / MRR@{K}.",
        "",
        "| Model | Text | " + " | ".join(groups) + " |",
        "|---|---|" + "---|" * len(groups),
    ]
    for key in models:
        spec = get_model(key)
        encoder = TorchEncoder(spec)
        texts = [i.text for i in items if i.source is None]
        queries = encoder.encode(texts, spec.query_prefix)
        for variant in variants:
            result = evaluate(items, passage_vectors(encoder, variant), queries, refs)
            cells = [f"{h:.2f} / {r:.2f} / {m:.2f}" for h, r, m, _ in (result[g] for g in groups)]
            lines.append(f"| {key} | {variant} | " + " | ".join(cells) + " |")
            print(lines[-1], flush=True)
    report = "\n".join(lines) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    return report


def run_pack_eval(
    sources: list[Source],
    pack_ids: list[str],
    dist: Path,
    out: Path,
    *,
    limit: RateLimit | None = None,
) -> str:
    """Evaluate built vector packs as the app uses them: stored verse vectors, queries
    embedded by the ONNX model pack (``local``) or the provider's API (``api``)."""
    import sqlite3  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    from contextlib import closing  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    from pipeline.build_embeddings import (  # noqa: PLC0415
        OnnxEncoder,
        api_vector_settings,
        model_spec,
        unpack_model,
        vector_settings,
    )
    from pipeline.build_translation import require_pack  # noqa: PLC0415

    by_id = {s.pack.id: s for s in sources if s.pack is not None}
    models = {i: s for i, s in by_id.items() if s.pack and s.pack.type == "model"}
    refs = verse_refs()
    items = load_items(data_dir() / "eval" / "semantic.toml", refs)
    groups = ["tr", "en", "ar", "related", "all"]
    lines = [
        "# Embedding evaluation of built vector packs",
        "",
        f"Cells: hit@{K} / recall@{K} / MRR@{K}. Sizes are the published files.",
        "",
        "| Vector pack | Model pack | Text | Size | " + " | ".join(groups) + " |",
        "|---|---|---|---|" + "---|" * len(groups),
    ]
    for pack_id in pack_ids:
        source = by_id.get(pack_id)
        if source is None or require_pack(source).type != "vectors":
            raise PipelineError(f"{pack_id}: not a vector pack")
        with closing(sqlite3.connect(dist / f"{pack_id}.sqlite")) as conn:
            blobs = [r[0] for r in conn.execute("SELECT embedding FROM vectors ORDER BY verse_id")]
        passages = np.stack([np.frombuffer(b, dtype="<f4") for b in blobs]).astype(np.float32)
        query_texts = [i.text for i in items if i.source is None]
        files = [f"{pack_id}.sqlite.zst"]
        if require_pack(source).meta.get("backend") == "api":
            api, text = api_vector_settings(source)
            model_id = f"{api.embedding_model} (API)"
            queries = encoder_for(api, limit).encode(query_texts, "query")
        else:
            model_source, text = vector_settings(source, models)
            model_id = require_pack(model_source).id
            spec = model_spec(model_source)
            with tempfile.TemporaryDirectory(prefix="siyak-eval-") as tmp:
                encoder = OnnxEncoder(unpack_model(dist / f"{model_id}.tar.zst", Path(tmp)), spec)
                queries = encoder.encode(query_texts, spec.query_prefix)
            files.append(f"{model_id}.tar.zst")
        result = evaluate(items, passages, queries, refs)
        size = sum((dist / name).stat().st_size for name in files)
        cells = [f"{h:.2f} / {r:.2f} / {m:.2f}" for h, r, m, _ in (result[g] for g in groups)]
        lines.append(
            f"| {pack_id} | {model_id} | {text} | {size / 1e6:.0f} MB | " + " | ".join(cells) + " |"
        )
        print(lines[-1], flush=True)
    report = "\n".join(lines) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    return report
