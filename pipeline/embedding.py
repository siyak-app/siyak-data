"""Embedding models and the verse texts they embed (app spec §7.4, ADR 0012 in the app).

Shared by ``eval_embeddings`` (which model and which text), ``export_model`` (model packs)
and ``build_vectors`` (vector packs). The ML libraries are an optional dependency group:
``uv sync --group embed``.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.errors import PipelineError
from pipeline.paths import cache_dir
from pipeline.tanzil import parse_quran_xml, parse_translation

VERSE_COUNT = 6236


@dataclass(frozen=True)
class ModelSpec:
    """A local embedding model as the app runs it (the model pack's metadata)."""

    key: str
    repo: str  # Hugging Face repository
    dim: int
    pooling: str  # 'mean', 'cls' or 'last'
    query_prefix: str
    passage_prefix: str
    license: str
    max_tokens: int = 512

    @property
    def embedding_model(self) -> str:
        """The canonical name of the embedding space (``local/<key>``)."""
        return f"local/{self.key}"


MODELS: dict[str, ModelSpec] = {
    spec.key: spec
    for spec in [
        ModelSpec(
            key="multilingual-e5-small",
            repo="intfloat/multilingual-e5-small",
            dim=384,
            pooling="mean",
            query_prefix="query: ",
            passage_prefix="passage: ",
            license="MIT",
        ),
        ModelSpec(
            key="multilingual-e5-base",
            repo="intfloat/multilingual-e5-base",
            dim=768,
            pooling="mean",
            query_prefix="query: ",
            passage_prefix="passage: ",
            license="MIT",
        ),
        ModelSpec(
            key="bge-m3",
            repo="BAAI/bge-m3",
            dim=1024,
            pooling="cls",
            query_prefix="",
            passage_prefix="",
            license="MIT",
        ),
        ModelSpec(
            key="qwen3-embedding-0.6b",
            repo="Qwen/Qwen3-Embedding-0.6B",
            dim=1024,
            pooling="last",
            # The model card's format: an instruction for queries, nothing for documents.
            query_prefix=(
                "Instruct: Given a question or a topic, retrieve verses of the Quran about it\n"
                "Query:"
            ),
            passage_prefix="",
            license="Apache-2.0",
        ),
    ]
}

# The translations a verse text may include. tr.diyanet is not used: it repeats the text
# of 843 verses for their neighbours (Tanzil's file merges verses), so neighbouring verses
# would share one vector.
TURKISH = "tr.vakfi"
ENGLISH = "en.pickthall"

# Which text is embedded for each verse (spec §18, question 2).
VARIANTS: dict[str, tuple[str, ...]] = {
    "ar": ("ar",),
    "tr": ("tr",),
    "en": ("en",),
    "ar+tr": ("ar", "tr"),
    "ar+tr+en": ("ar", "tr", "en"),
}


def get_model(key: str) -> ModelSpec:
    """Return a model by key or raise a PipelineError naming the known keys."""
    try:
        return MODELS[key]
    except KeyError:
        raise PipelineError(f"unknown model {key!r}; known: {', '.join(MODELS)}") from None


def verse_refs() -> list[tuple[int, int]]:
    """(surah, ayah) of every verse; index + 1 is the verse id (Mushaf order)."""
    text = parse_quran_xml(cache_dir() / "tanzil" / "quran-simple-clean.xml")
    refs = [(v.surah, v.ayah) for v in text.verses]
    if len(refs) != VERSE_COUNT:
        raise PipelineError(f"expected {VERSE_COUNT} verses, found {len(refs)}")
    return refs


def verse_texts(variant: str) -> list[str]:
    """The text embedded for each verse, in verse id order.

    Arabic is Tanzil's Simple Clean text (no diacritics); parts are joined by a line break.
    """
    try:
        parts = VARIANTS[variant]
    except KeyError:
        raise PipelineError(f"unknown text {variant!r}; known: {', '.join(VARIANTS)}") from None
    arabic = parse_quran_xml(cache_dir() / "tanzil" / "quran-simple-clean.xml").verses
    columns: list[list[str]] = []
    for part in parts:
        if part == "ar":
            columns.append([v.text for v in arabic])
            continue
        source = TURKISH if part == "tr" else ENGLISH
        verses = parse_translation(cache_dir() / source / f"{source}.txt").verses
        try:
            columns.append([verses[(v.surah, v.ayah)] for v in arabic])
        except KeyError as exc:
            raise PipelineError(f"{source}: verse {exc.args[0]} is missing") from None
    return ["\n".join(row) for row in zip(*columns, strict=True)]
