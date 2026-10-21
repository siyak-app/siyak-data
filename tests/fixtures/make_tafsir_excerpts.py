"""Write the tafsir fixture excerpts from the pinned Quranpedia dumps in .cache/.

The excerpt keeps the dump's ``license``, ``book`` and ``schema`` and the
complete entries of the listed surahs, unchanged (only the JSON whitespace
differs). Quranpedia's license allows republishing part of the data with
credit and the dump version (tests/fixtures/README.md).

    uv run python tests/fixtures/make_tafsir_excerpts.py
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCERPTS = {
    "ar.jalalayn": ("tafsir-book-272.json.gz", {1, 97, 112, 113, 114}),
    "ar.razi": ("tafsir-book-352.json.gz", {97, 112, 113, 114}),
}


def excerpt(source: Path, surahs: set[int]) -> bytes:
    data = json.loads(gzip.decompress(source.read_bytes()))
    data["ayahs"] = [e for e in data["ayahs"] if e["surah"] in surahs]
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(text, mtime=0)


def main() -> None:
    for pack_id, (name, surahs) in EXCERPTS.items():
        out = ROOT / "tests" / "fixtures" / "cache" / pack_id / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(excerpt(ROOT / ".cache" / pack_id / name, surahs))
        print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
