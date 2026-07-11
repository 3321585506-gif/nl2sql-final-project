"""
Build and load runtime artifacts for the NL2SQL pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.index_builder import (
    build_all_indexes,
    build_entity_indexes,
    build_value_index,
)
from src.schema_graph import build_schema_graph
from src.schema_parser import build_schema_catalog, parse_sqlite_schema


ARTIFACT_FILES = {
    "schema_catalog": "schema_catalog.json",
    "alias_map": "alias_map.json",
    "inverted_index": "inverted_index.json",
    "value_index": "value_index.json",
    "entity_indexes": "entity_indexes.json",
    "schema_graph": "schema_graph.json",
}


def build_all_artifacts(db_path: str, output_dir: str) -> None:
    """
    Build all preprocessing artifacts under output_dir.
    """
    db = Path(db_path)
    if not db.exists():
        raise FileNotFoundError(f"database not found: {db_path}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    schema_info = parse_sqlite_schema(str(db))
    schema_catalog = build_schema_catalog(str(db))
    indexes = build_all_indexes(schema_info)
    value_index = build_value_index(schema_catalog)
    entity_indexes = build_entity_indexes(schema_catalog)
    schema_graph = build_schema_graph(schema_info)

    payloads = {
        "schema_catalog": schema_catalog,
        "alias_map": indexes["alias_map"],
        "inverted_index": indexes["inverted_index"],
        "value_index": value_index,
        "entity_indexes": entity_indexes,
        "schema_graph": schema_graph,
    }

    for name, payload in payloads.items():
        _write_json(payload, out / ARTIFACT_FILES[name])

    print(f"Artifacts saved to: {out}")


def load_runtime_artifacts(processed_dir: str) -> dict[str, Any]:
    """
    Load runtime artifacts built by build_all_artifacts.
    """
    root = Path(processed_dir)
    missing = [filename for filename in ARTIFACT_FILES.values() if not (root / filename).exists()]
    if missing:
        missing_text = ", ".join(missing)
        raise FileNotFoundError(
            f"missing runtime artifacts in {root}: {missing_text}; "
            "run `python scripts/build_artifacts.py` first"
        )

    artifacts = {}
    for name, filename in ARTIFACT_FILES.items():
        artifacts[name] = _read_json(root / filename)
    return artifacts


def _write_json(payload: Any, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    print(f"  wrote {path.name} ({path.stat().st_size / 1024:.1f} KB)")


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    from src.config import DB_PATH, PROCESSED_DATA_DIR

    build_all_artifacts(str(DB_PATH), str(PROCESSED_DATA_DIR))
