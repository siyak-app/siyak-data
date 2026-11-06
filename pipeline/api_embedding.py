"""Verse vectors from an embedding API (app spec §6.1, §7.4; docs/pack-format.md §4.9).

An ``api`` vector pack is built once here with the maintainers' key; the app embeds only
the queries, with the user's key, in the same space. :class:`ApiEncoder` sends texts
exactly as the app's ``embed/api.rs`` does (model, output dimension, prefixes, Gemini's
task type, Voyage's input type) and normalizes the vectors, so both sides agree.

Gemini and Voyage are built here. The key comes from ``GEMINI_API_KEY`` (or
``GEMINI_API``) or ``VOYAGE_API_KEY`` (or ``VOYAGE_API``); it is sent only to the
provider's host and never written anywhere. Batches are cached under
``.cache/embeddings/api/`` as they arrive, so an interrupted build resumes without paying
for the same texts twice. A :class:`RateLimit` paces the requests for accounts with low
limits (a Voyage account without a payment method).
"""

from __future__ import annotations

import math
import os
import time
from collections import deque
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

#: Texts per cache file and at most per request, as in the app (Gemini takes at most 100).
BATCH = 96
#: Environment variables that may hold each provider's key, in order.
KEY_VARS = {
    "gemini": ("GEMINI_API_KEY", "GEMINI_API"),
    "voyage": ("VOYAGE_API_KEY", "VOYAGE_API"),
}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
VOYAGE_BASE = "https://api.voyageai.com/v1"
BASES = {"gemini": GEMINI_BASE, "voyage": VOYAGE_BASE}
TIMEOUT = httpx.Timeout(120.0, connect=20.0)
#: Attempts per request on rate limits (429) and server errors (5xx).
ATTEMPTS = 8
#: Longest wait the provider may ask for before a build gives up for now: a longer one
#: (a daily quota) is not worth waiting for in one run.
MAX_RETRY_DELAY = 120.0
#: UTF-8 bytes per token assumed before the provider has reported a count. Low, so the
#: first requests are rather too small than too large for a token limit.
BYTES_PER_TOKEN = 2.0
WINDOW = 60.0

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


@dataclass(frozen=True)
class RateLimit:
    """Requests and tokens per minute the account allows; ``None`` is no limit."""

    rpm: int | None = None
    tpm: int | None = None

    def request_tokens(self) -> float:
        """Most tokens one request should carry so the limits are kept."""
        if self.tpm is None:
            return math.inf
        return self.tpm / self.rpm if self.rpm else float(self.tpm)


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
    task_type = bool(meta.get("task_type", False))
    if task_type and provider != "gemini":
        raise PipelineError(f"{where}: task_type is only for gemini")
    return ApiSpec(
        provider=provider,
        model=model,
        embedding_model=embedding_model,
        dim=dim,
        query_prefix=str(meta.get("query_prefix", "")),
        passage_prefix=str(meta.get("passage_prefix", "")),
        task_type=task_type,
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
    """POST ``body`` as JSON; never follows redirects (the key stays with the provider).

    A network failure (no connection, a timeout) is status 0, retried like a 5xx.
    """
    try:
        response = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT)
    except httpx.TransportError as exc:
        return 0, {"detail": f"network error: {type(exc).__name__}"}
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return response.status_code, payload


class Limiter:
    """Keeps requests and tokens within a :class:`RateLimit` over a sliding minute."""

    def __init__(
        self,
        limit: RateLimit,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.limit = limit
        self.clock = clock
        self.sleep = sleep
        self.sent: deque[tuple[float, float]] = deque()

    def wait(self, tokens: float) -> None:
        """Sleep until a request of about ``tokens`` tokens fits the limits."""
        while True:
            now = self.clock()
            while self.sent and self.sent[0][0] <= now - WINDOW:
                self.sent.popleft()
            used = sum(t for _, t in self.sent)
            rpm, tpm = self.limit.rpm, self.limit.tpm
            fits_rpm = rpm is None or len(self.sent) < rpm
            fits_tpm = tpm is None or not self.sent or used + tokens <= tpm
            if fits_rpm and fits_tpm:
                return
            self.sleep(self.sent[0][0] + WINDOW - now + 0.5)

    def record(self, tokens: float) -> None:
        """Count a request that was just answered."""
        self.sent.append((self.clock(), tokens))


class ApiEncoder:
    """Embeds texts with an API the way the app's ``ApiEmbedder`` does."""

    def __init__(
        self,
        spec: ApiSpec,
        key: str,
        post: Post = http_post,
        *,
        base: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        limit: RateLimit | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.spec = spec
        self.key = key
        self.post = post
        self.base = base or BASES[spec.provider]
        self.sleep = sleep
        self.limit = limit or RateLimit()
        self.limiter = Limiter(self.limit, clock, sleep)
        self.bytes_per_token = BYTES_PER_TOKEN

    def url(self) -> str:
        """The provider's embedding endpoint."""
        if self.spec.provider == "gemini":
            return f"{self.base}/models/{self.spec.model}:batchEmbedContents"
        return f"{self.base}/embeddings"

    def headers(self) -> dict[str, str]:
        """The key, as the provider wants it."""
        if self.spec.provider == "gemini":
            return {"x-goog-api-key": self.key}
        return {"Authorization": f"Bearer {self.key}"}

    def body(self, texts: Sequence[str], kind: str) -> dict[str, Any]:
        """The request body for already prefixed ``texts``; ``kind`` is query or passage."""
        if self.spec.provider == "voyage":
            return {
                "model": self.spec.model,
                "input": list(texts),
                "input_type": "query" if kind == "query" else "document",
                "output_dimension": self.spec.dim,
            }
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

    def parse(self, payload: Any) -> tuple[list[Any], int | None]:
        """The vectors of a successful response, in input order, and its token count."""
        try:
            if self.spec.provider == "voyage":
                data = sorted(payload["data"], key=lambda d: int(d["index"]))
                tokens = payload.get("usage", {}).get("total_tokens")
                return [d["embedding"] for d in data], int(tokens) if tokens else None
            return [e["values"] for e in payload["embeddings"]], None
        except (KeyError, TypeError, ValueError, AttributeError):
            raise PipelineError(f"{self.spec.provider}: unexpected response") from None

    def estimate(self, text: str) -> float:
        """Tokens ``text`` probably takes."""
        return len(text.encode("utf-8")) / self.bytes_per_token

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
        """Embed one cache batch, in as many requests as the rate limit needs."""
        import numpy as np  # noqa: PLC0415

        values: list[Any] = []
        done = 0
        while done < len(texts):
            part = self._next_part(texts[done:])
            values += self._request(part, kind)
            done += len(part)
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

    def _next_part(self, texts: list[str]) -> list[str]:
        """The leading texts that fit :meth:`RateLimit.request_tokens` (at least one), by
        the latest estimate: each answer refines it, so the parts follow the real sizes."""
        most = self.limit.request_tokens()
        size = 0.0
        for count, text in enumerate(texts):
            size += self.estimate(text)
            if count and size > most:
                return texts[:count]
        return texts

    def _request(self, texts: list[str], kind: str) -> list[Any]:
        estimate = sum(self.estimate(t) for t in texts)
        body = self.body(texts, kind)
        delay = 2.0
        for attempt in range(ATTEMPTS):
            self.limiter.wait(estimate)
            status, payload = self.post(self.url(), self.headers(), body)
            if status == 200:
                values, tokens = self.parse(payload)
                if tokens:
                    # Learn the real ratio, keeping a margin for longer texts.
                    sent = sum(len(t.encode("utf-8")) for t in texts)
                    self.bytes_per_token = sent / tokens * 0.9
                self.limiter.record(tokens or estimate)
                return values
            self.limiter.record(estimate)
            wait = retry_delay(payload)
            retry = status in {0, 429} or status >= 500
            if retry and attempt + 1 < ATTEMPTS and (wait is None or wait <= MAX_RETRY_DELAY):
                self.sleep(delay if wait is None else wait + 1.0)
                delay = min(delay * 2, 60.0)
                continue
            raise PipelineError(f"{self.spec.provider}: HTTP {status}: {error_message(payload)}")
        raise PipelineError(f"{self.spec.provider}: no answer after {ATTEMPTS} attempts")


def error_message(payload: Any) -> str:
    """The provider's error message, short (Gemini: ``error.message``, Voyage: ``detail``)."""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message", ""))[:300]
        if "detail" in payload:
            return str(payload["detail"])[:300]
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


def encoder_for(spec: ApiSpec, limit: RateLimit | None = None) -> ApiEncoder:
    """An encoder with the key from the environment."""
    return ApiEncoder(spec, api_key(spec.provider), limit=limit)


def passage_cache(spec: ApiSpec, text: str) -> Path:
    """Where the verse vectors of ``spec`` and verse text ``text`` are cached."""
    return cache_dir() / "embeddings" / "api" / spec.cache_key / text
