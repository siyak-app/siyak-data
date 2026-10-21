"""The normalization contract: tests/normalize_vectors.json is shared with the app (Rust)."""

import json
from pathlib import Path
from typing import Any

import pytest

from pipeline.normalize import RULE_IDS, normalize, rule_counts
from pipeline.tanzil import parse_quran_xml

VECTORS_FILE = Path(__file__).parent / "normalize_vectors.json"
VECTORS: list[dict[str, Any]] = json.loads(VECTORS_FILE.read_text(encoding="utf-8"))["vectors"]
CACHE = Path(__file__).parent.parent / ".cache" / "tanzil"

#: Rules that may change Tanzil's Simple Clean text: letter unification only.
CLEAN_TEXT_RULES = {"N5", "N6", "N7", "N8", "N9"}


def tanzil_texts(path: Path) -> list[str]:
    return [aya.text for aya in parse_quran_xml(path).verses]


@pytest.mark.parametrize("vector", VECTORS, ids=[v["id"] for v in VECTORS])
def test_vector(vector: dict[str, Any]) -> None:
    assert normalize(vector["input"]) == vector["expected"]


@pytest.mark.parametrize("vector", VECTORS, ids=[v["id"] for v in VECTORS])
def test_vector_lists_exactly_the_rules_it_exercises(vector: dict[str, Any]) -> None:
    assert set(rule_counts([vector["input"]])) == set(vector["rules"])


@pytest.mark.parametrize("vector", VECTORS, ids=[v["id"] for v in VECTORS])
def test_idempotent_on_vectors(vector: dict[str, Any]) -> None:
    once = normalize(vector["input"])
    assert normalize(once) == once
    assert normalize(vector["expected"]) == vector["expected"]


def test_vector_set_is_complete() -> None:
    assert len(VECTORS) >= 50
    assert len({v["id"] for v in VECTORS}) == len(VECTORS)
    covered = {rule for v in VECTORS for rule in v["rules"]}
    assert covered == set(RULE_IDS)
    assert sum(1 for v in VECTORS if v.get("source", "").startswith("tanzil")) >= 20


@pytest.mark.full
@pytest.mark.skipif(not (CACHE / "quran-uthmani.xml").exists(), reason="no cached Tanzil text")
def test_idempotent_on_full_uthmani_text() -> None:
    for text in tanzil_texts(CACHE / "quran-uthmani.xml"):
        once = normalize(text)
        assert normalize(once) == once


@pytest.mark.full
@pytest.mark.skipif(not (CACHE / "quran-simple-clean.xml").exists(), reason="no cached Tanzil text")
def test_simple_clean_is_changed_only_by_letter_rules() -> None:
    texts = tanzil_texts(CACHE / "quran-simple-clean.xml")
    assert set(rule_counts(texts)) <= CLEAN_TEXT_RULES
    for text in texts:
        once = normalize(text)
        assert normalize(once) == once
