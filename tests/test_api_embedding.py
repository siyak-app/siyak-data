"""API vector packs (pipeline/api_embedding.py): requests as the app sends them, no network."""

from pathlib import Path
from typing import Any

import pytest

from pipeline.api_embedding import BATCH, ApiEncoder, api_key, api_spec, retry_delay
from pipeline.build_embeddings import api_vector_settings
from pipeline.errors import PipelineError
from pipeline.paths import repo_root
from pipeline.sources import load_source

META: dict[str, Any] = {
    "embedding_model": "gemini/gemini-embedding-2",
    "dim": 4,
    "normalized": True,
    "backend": "api",
    "provider": "gemini",
    "api_model": "gemini-embedding-2",
    "api_dimensions": 4,
    "query_prefix": "task: search result | query: ",
    "passage_prefix": "title: none | text: ",
}


class FakeGemini:
    """Answers batchEmbedContents with vectors of length 2 (so they need normalizing)."""

    def __init__(self, failures: int = 0) -> None:
        self.calls: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        self.failures = failures

    def __call__(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> tuple[int, Any]:
        self.calls.append((url, headers, body))
        if self.failures:
            self.failures -= 1
            return 429, {"error": {"message": "Resource exhausted"}}
        values = [
            [2.0 if j == i % 4 else 0.0 for j in range(4)] for i in range(len(body["requests"]))
        ]
        return 200, {"embeddings": [{"values": v} for v in values]}


def test_the_spec_is_read_and_checked() -> None:
    spec = api_spec(META, "x")
    assert (spec.provider, spec.model, spec.dim, spec.task_type) == (
        "gemini",
        "gemini-embedding-2",
        4,
        False,
    )
    assert spec.cache_key == "gemini_gemini-embedding-2-4"
    for key, value in [
        ("backend", "local"),
        ("provider", "voyage"),
        ("embedding_model", "openai/x"),
        ("api_dimensions", 8),
        ("normalized", False),
        ("api_model", ""),
    ]:
        with pytest.raises(PipelineError):
            api_spec({**META, key: value}, "x")


def test_requests_match_the_app() -> None:
    np = pytest.importorskip("numpy")
    fake = FakeGemini()
    encoder = ApiEncoder(api_spec({**META, "task_type": True}, "x"), "AIza-test", post=fake)
    vectors = encoder.encode(["sabır", "namaz"], "query")
    url, headers, body = fake.calls[0]
    assert url.endswith("/v1beta/models/gemini-embedding-2:batchEmbedContents")
    assert headers == {"x-goog-api-key": "AIza-test"}
    assert body["requests"][0] == {
        "model": "models/gemini-embedding-2",
        "content": {"parts": [{"text": "task: search result | query: sabır"}]},
        "taskType": "RETRIEVAL_QUERY",
        "outputDimensionality": 4,
    }
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1)

    encoder.encode(["p"], "passage")
    passage = fake.calls[1][2]["requests"][0]
    assert passage["content"]["parts"][0]["text"] == "title: none | text: p"
    assert passage["taskType"] == "RETRIEVAL_DOCUMENT"


def test_rate_limits_are_retried_and_errors_reported() -> None:
    pytest.importorskip("numpy")
    waits: list[float] = []
    fake = FakeGemini(failures=2)
    encoder = ApiEncoder(api_spec(META, "x"), "k", post=fake, sleep=waits.append)
    assert encoder.encode(["a"], "query").shape == (1, 4)
    assert waits == [2.0, 4.0]

    def rejected(_url: str, _headers: dict[str, str], _body: dict[str, Any]) -> tuple[int, Any]:
        return 400, {"error": {"message": "API key not valid"}}

    with pytest.raises(PipelineError, match="HTTP 400: API key not valid"):
        ApiEncoder(api_spec(META, "x"), "k", post=rejected).encode(["a"], "query")


def test_batches_are_cached_and_reused(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    texts = [f"t{i}" for i in range(BATCH + 3)]
    fake = FakeGemini()
    first = ApiEncoder(api_spec(META, "x"), "k", post=fake).encode(texts, "passage", tmp_path)
    assert len(fake.calls) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["00000.npy", "00096.npy"]
    (tmp_path / "00096.npy").unlink()  # as if the build stopped after the first batch
    again = FakeGemini()
    second = ApiEncoder(api_spec(META, "x"), "k", post=again).encode(texts, "passage", tmp_path)
    assert len(again.calls) == 1, "only the missing batch was requested"
    assert (first == second).all()


def test_the_key_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API", raising=False)
    with pytest.raises(PipelineError, match="GEMINI_API_KEY or GEMINI_API"):
        api_key("gemini")
    monkeypatch.setenv("GEMINI_API", " k2 ")
    assert api_key("gemini") == "k2"


def test_the_gemini_pack_is_declared_as_the_app_reads_it() -> None:
    source = load_source(repo_root() / "sources" / "vectors" / "gemini-embedding-2" / "source.toml")
    spec, text = api_vector_settings(source)
    assert text == "ar+tr+en"
    assert spec.dim == 1024
    assert source.pack is not None
    assert source.pack.requires == ()
    assert not source.pack.publish


def quota_error(delay: str | None, message: str = "Quota exceeded") -> dict[str, Any]:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]
    return {"error": {"code": 429, "message": message, "details": details if delay else []}}


def test_the_provider_s_retry_delay_is_followed() -> None:
    assert retry_delay(quota_error("37s")) == 37.0
    assert retry_delay(quota_error(None)) is None
    daily = quota_error(None, "Quota exceeded for metric: ...requests_per_day")
    daily["error"]["details"] = [{"quotaId": "EmbedContentRequestsPerDayPerProject"}]
    daily["error"]["message"] = "Quota exceeded per day"
    assert retry_delay(daily) == float("inf")
    assert retry_delay(None) is None


def test_a_spent_quota_stops_at_once_and_says_how_far_it_got(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    waits: list[float] = []
    answers = iter([None, quota_error("3600s")])

    def post(url: str, headers: dict[str, str], body: dict[str, Any]) -> tuple[int, Any]:
        answer = next(answers)
        if answer is None:
            return FakeGemini()(url, headers, body)
        return 429, answer

    encoder = ApiEncoder(api_spec(META, "x"), "k", post=post, sleep=waits.append)
    texts = [f"t{i}" for i in range(BATCH + 1)]
    with pytest.raises(PipelineError, match=r"96/97 texts embedded and cached; run the same"):
        encoder.encode(texts, "passage", tmp_path)
    assert waits == [], "an hour-long wait is not waited for"
    assert (tmp_path / "00000.npy").exists()
