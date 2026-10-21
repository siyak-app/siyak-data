"""``pricing.json`` (spec §9.4) from ``data/pricing.toml``."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from pipeline.errors import PipelineError
from pipeline.paths import data_dir


def build_pricing(out: Path, source: Path | None = None) -> Path:
    """Write ``out`` from the pricing TOML file and return its path."""
    path = source or data_dir() / "pricing.toml"
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    models: dict[str, Any] = data.get("models", {})
    for name, prices in models.items():
        if set(prices) != {"input_per_mtok", "output_per_mtok"}:
            raise PipelineError(f"{path}: model '{name}' needs input_per_mtok and output_per_mtok")
    pricing = {
        "updated_at": str(data["updated_at"]),
        "currency": str(data["currency"]),
        "models": {name: models[name] for name in sorted(models)},
    }
    out.write_text(json.dumps(pricing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out
