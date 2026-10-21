import os
from pathlib import Path

import pytest

from pipeline.build import run_build

FIXTURES = Path(__file__).parent / "fixtures"
EPOCH = "1792540800"  # 2026-10-21T00:00:00Z


def fixture_env(dist: Path) -> dict[str, str]:
    return {
        "SIYAK_DATA_SOURCES": str(FIXTURES / "sources"),
        "SIYAK_DATA_CACHE": str(FIXTURES / "cache"),
        "SIYAK_DATA_DIST": str(dist),
        "SOURCE_DATE_EPOCH": EPOCH,
    }


@pytest.fixture
def fixtures_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the pipeline at the committed fixtures; return the (empty) dist dir."""
    dist = tmp_path / "dist"
    for key, value in fixture_env(dist).items():
        monkeypatch.setenv(key, value)
    return dist


@pytest.fixture(scope="session")
def built_fixtures(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the fixture profile once per session; return the dist dir.

    The environment is restored right after the build so it does not leak into
    other tests; tests that read sources again use ``fixture_sources``.
    """
    dist = tmp_path_factory.mktemp("dist")
    saved = dict(os.environ)
    os.environ.update(fixture_env(dist))
    try:
        run_build()
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return dist


@pytest.fixture
def fixture_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use fixture sources/cache without building."""
    monkeypatch.setenv("SIYAK_DATA_SOURCES", str(FIXTURES / "sources"))
    monkeypatch.setenv("SIYAK_DATA_CACHE", str(FIXTURES / "cache"))
