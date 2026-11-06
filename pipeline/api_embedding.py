"""Verse vectors from an embedding API (app spec §6.1, §7.4; docs/pack-format.md §4.6).

An ``api`` vector pack is built once here with the maintainers' key; the app embeds only
the queries, with the user's key, in the same space. :class:`ApiEncoder` sends texts
exactly as the app's ``embed/api.rs`` does (model, output dimension, prefixes, Gemini's
task type, batches of 96) and normalizes the vectors, so both sides agree.

Only Gemini is built here so far. The key comes from ``GEMINI_API_KEY`` (or
``GEMINI_API``); it is sent only to the provider's host and never written anywhere.
Batches are cached under ``.cache/embeddings/api/`` as they arrive, so an interrupted
build resumes without paying for the same texts twice.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from pipeline.errors import PipelineError
from pipeline.paths import cache_dir

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    Matrix = npt.NDArray[np.float32]

#: Texts per request, as in the app (Gemini takes at most 100).
BATCH = 96
#: Environment variables that may hold each provider's key, in order.
KEY_VARS = {"gemini": ("GEMINI_API_KEY", "GEMINI_API")}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = httpx.Timeout(120.0, connect=20.0)
#: Attempts per batch on rate limits (429) and server errors (5xx).
ATTEMPTS = 8
#: Longest wait the provider may ask for before a build gives up for now: a longer one
#: (a daily quota) is not worth waiting for in one run.
MAX_RETRY_DELAY = 120.0

#: Sends one JSON request: (url, headers, body) -> (status, parsed body).
Post = Callable[[str, dict[str, str], dict[str, Any]], tuple[int, Any]]


@dataclass(frozen=True)
class ApiSpec:
    """How an ``api`` vector pack's texts are embedded (its ``[pack.meta]``)."""

    provider: str
    model: str  # the provider's model id
    embedding_model: str  # canonical, e.g. gemini/gemini-embedding-2
    dim: int
    query_prefix: str
    passage_prefix: str
    task_type: bool

    @property
    def cache_key(self) -> str:
        """Directory name of the cached vectors: the space plus how texts were sent."""
        task = "-task" if self.task_type else ""
        return f"{self.embedding_model.replace('/', '_')}-{self.dim}{task}"


def api_spec(meta: dict[str, Any], where: str) -> ApiSpec:
    """Read and check the metadata of an ``api`` vector pack."""
    provider = str(meta.get("provider", ""))
    if meta.get("backend") != "api":
        raise PipelineError(f"{where}: backend must be 'api'")
    if provider not in KEY_VARS:
        raise PipelineError(f"{where}: provider must be one of {', '.join(KEY_VARS)} here")
    embedding_model = str(meta.get("embedding_model", ""))
    if not embedding_model.startswith(f"{provider}/"):
        raise PipelineError(f"{where}: embedding_model must start with {provider}/")
    model = str(meta.get("api_model", ""))
    dim = int(meta.get("dim", 0))
    if not model or dim <= 0:
        raise PipelineError(f"{where}: api_model and dim are required")
    if meta.get("api_dimensions", dim) != dim:
        raise PipelineError(f"{where}: api_dimensions must equal dim")
    if meta.get("normalized") is not True:
        raise PipelineError(f"{where}: normalized must be true")
    return ApiSpec(
        provider=provider,
        model=model,
        embedding_model=embedding_model,
        dim=dim,
        query_prefix=str(meta.get("query_prefix", "")),
        passage_prefix=str(meta.get("passage_prefix", "")),
        task_type=bool(meta.get("task_type", False)),
    )


def api_key(provider: str) -> str:
    """The provider's key from the environment."""
    for var in KEY_VARS[provider]:
        key = os.environ.get(var, "").strip()
        if key:
            return key
    names = " or ".join(KEY_VARS[provider])
    raise PipelineError(f"set {names} to build {provider} vector packs")


def http_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> tuple[int, Any]:
    """POST ``body`` as JSON; never follows redirects (the key stays with the provider)."""
    response = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT)
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return response.status_code, payload


class ApiEncoder:
    """Embeds texts with an API the way the app's ``ApiEmbedder`` does."""

    def __init__(
        self,
        spec: ApiSpec,
        key: str,
        post: Post = http_post,
        base: str = GEMINI_BASE,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.spec = spec
        self.key = key
        self.post = post
        self.base = base
        self.sleep = sleep

    def body(self, texts: Sequence[str], kind: str) -> dict[str, Any]:
        """The request body for already prefixed ``texts``; ``kind`` is query or passage."""
        requests = []
        for text in texts:
            request: dict[str, Any] = {
                "model": f"models/{self.spec.model}",
                "content": {"parts": [{"text": text}]},
            }
            if self.spec.task_type:
                request["taskType"] = "RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT"
            request["outputDimensionality"] = self.spec.dim
            requests.append(request)
        return {"requests": requests}

    def encode(self, texts: Sequence[str], kind: str, cache: Path | None = None) -> Matrix:
        """Unit vectors of ``prefix + text``, one row per text.

        With ``cache``, each batch is saved there (``<first index>.npy``) and reused.
        """
        import numpy as np  # noqa: PLC0415 (optional dependency)

        prefix = self.spec.query_prefix if kind == "query" else self.spec.passage_prefix
        rows = []
        for start in range(0, len(texts), BATCH):
            batch = [prefix + t for t in texts[start : start + BATCH]]
            path = cache / f"{start:05d}.npy" if cache else None
            if path and path.exists():
                cached: Matrix = np.load(path)
                if cached.shape == (len(batch), self.spec.dim):
                    rows.append(cached)
                    continue
            try:
                vectors = self._batch(batch, kind)
            except PipelineError as err:
                if cache is None:
                    raise
                raise PipelineError(
                    f"{err} ({start}/{len(texts)} texts embedded and cached; "
                    "run the same command again to continue)"
                ) from None
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                np.save(path, vectors)
            rows.append(vectors)
            if cache:
                print(f"  embedded {min(start + BATCH, len(texts))}/{len(texts)}", flush=True)
        if not rows:
            return np.zeros((0, self.spec.dim), np.float32)
        result: Matrix = np.concatenate(rows)
        return result

    def _batch(self, texts: list[str], kind: str) -> Matrix:
        import numpy as np  # noqa: PLC0415

        url = f"{self.base}/models/{self.spec.model}:batchEmbedContents"
        headers = {"x-goog-api-key": self.key}
        body = self.body(texts, kind)
        delay = 2.0
        for attempt in range(ATTEMPTS):
            status, payload = self.post(url, headers, body)
            if status == 200:
                break
            wait = retry_delay(payload)
            retry = status == 429 or status >= 500
            if retry and attempt + 1 < ATTEMPTS and (wait is None or wait <= MAX_RETRY_DELAY):
                self.sleep(delay if wait is None else wait + 1.0)
                delay = min(delay * 2, 60.0)
                continue
            raise PipelineError(f"{self.spec.provider}: HTTP {status}: {error_message(payload)}")
        try:
            values = [e["values"] for e in payload["embeddings"]]
        except (KeyError, TypeError):
            raise PipelineError(f"{self.spec.provider}: unexpected response") from None
        vectors = np.asarray(values, dtype=np.float32)
        if vectors.shape != (len(texts), self.spec.dim):
            raise PipelineError(
                f"{self.spec.provider}: got {vectors.shape}, expected ({len(texts)}, "
                f"{self.spec.dim})"
            )
        if not np.isfinite(vectors).all():
            raise PipelineError(f"{self.spec.provider}: a vector is not finite")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if not (norms > 0).all():
            raise PipelineError(f"{self.spec.provider}: a vector is zero")
        normalized: Matrix = (vectors / norms).astype(np.float32)
        return normalized


def error_message(payload: Any) -> str:
    """The provider's error message, short."""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message", ""))[:300]
    return ""


def retry_delay(payload: Any) -> float | None:
    """Seconds the provider asks to wait (Gemini's ``RetryInfo.retryDelay``, e.g. ``"37s"``).

    A quota error without one (a daily quota) counts as an endless wait.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return None
    error = payload["error"]
    for detail in error.get("details", []) or []:
        if isinstance(detail, dict) and str(detail.get("@type", "")).endswith("RetryInfo"):
            text = str(detail.get("retryDelay", "")).removesuffix("s")
            try:
                return float(text)
            except ValueError:
                return None
    if "quota" in str(error.get("message", "")).lower() and "per day" in str(error).lower():
        return float("inf")
    return None


def encoder_for(spec: ApiSpec) -> ApiEncoder:
    """An encoder with the key from the environment."""
    return ApiEncoder(spec, api_key(spec.provider))


def passage_cache(spec: ApiSpec, text: str) -> Path:
    """Where the verse vectors of ``spec`` and verse text ``text`` are cached."""
    return cache_dir() / "embeddings" / "api" / spec.cache_key / text
