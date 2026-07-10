"""
串联完整流程，批量处理测试集。

负责人：B
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    from . import config
    from .llm_client import LLMClient
    from .sql_generator import generate_sql_for_question
    from .submission_writer import build_submission, save_submission
except ImportError:
    import config
    from llm_client import LLMClient
    from sql_generator import generate_sql_for_question
    from submission_writer import build_submission, save_submission


def run_pipeline(test_file: str, output_path: str) -> None:
    """
    读取测试集，批量生成 SQL，保存提交文件。
    """
    schema_info = _load_schema_info()
    indexes = _load_indexes(schema_info)
    graph = _load_schema_graph(schema_info)
    llm_client = LLMClient(
        provider=os.getenv("LLM_PROVIDER", config.LLM_PROVIDER),
        model=os.getenv("LLM_MODEL", config.LLM_MODEL),
    )

    queries = _load_test_queries(test_file)
    predictions = []
    for item in queries:
        question = item.get("query") or item.get("question") or ""
        result = generate_sql_for_question(
            question=question,
            schema_info=schema_info,
            indexes=indexes,
            graph=graph,
            llm_client=llm_client,
        )
        predictions.append(
            {
                "id": item.get("id", len(predictions)),
                "query": question,
                "predicted_sql": result.get("predicted_sql", ""),
                "latency": result.get("latency", 0.0),
            }
        )

    submission = build_submission(config.TEAM_ID, predictions)
    save_submission(submission, output_path)


def _load_test_queries(test_file: str) -> list[dict]:
    path = Path(test_file)
    try:
        from .data_loader import load_test_queries
    except ImportError:
        try:
            from data_loader import load_test_queries
        except ImportError:
            load_test_queries = None
    if load_test_queries is not None:
        try:
            return load_test_queries(str(path))
        except NotImplementedError:
            pass

    if path.suffix.lower() == ".jsonl":
        items = []
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file):
                if not line.strip():
                    continue
                item = json.loads(line)
                item.setdefault("id", str(line_number))
                items.append(item)
        return items

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, dict):
        data = data.get("results") or data.get("data") or data.get("queries") or []
    return [item if isinstance(item, dict) else {"id": index, "query": str(item)} for index, item in enumerate(data)]


def _load_schema_info() -> dict:
    db_path = str(config.DB_PATH)
    try:
        from .schema_parser import parse_sqlite_schema
    except ImportError:
        try:
            from schema_parser import parse_sqlite_schema
        except ImportError:
            parse_sqlite_schema = None
    if parse_sqlite_schema is not None and Path(db_path).exists():
        try:
            return parse_sqlite_schema(db_path)
        except NotImplementedError:
            pass
    raise RuntimeError("schema_info is not available. Please let A finish schema_parser.py or provide a SQLite database.")


def _load_indexes(schema_info: dict) -> dict:
    try:
        from .index_builder import build_alias_map, build_inverted_index
    except ImportError:
        try:
            from index_builder import build_alias_map, build_inverted_index
        except ImportError:
            return {}
    try:
        alias_map = build_alias_map(schema_info)
        inverted_index = build_inverted_index(schema_info, alias_map)
        return {"alias_map": alias_map, "inverted_index": inverted_index}
    except NotImplementedError:
        return {}


def _load_schema_graph(schema_info: dict) -> dict:
    try:
        from .schema_graph import build_schema_graph
    except ImportError:
        try:
            from schema_graph import build_schema_graph
        except ImportError:
            return {}
    try:
        return build_schema_graph(schema_info)
    except NotImplementedError:
        return {}


def run_pipeline_with_context(
    test_file: str,
    output_path: str,
    schema_info: dict,
    indexes: dict | None = None,
    graph: dict | None = None,
    llm_client: Any | None = None,
) -> None:
    """
    使用已准备好的 schema/index/graph 运行 B 侧流程，便于 A 模块未完成时做集成测试。
    """
    queries = _load_test_queries(test_file)
    client = llm_client or LLMClient("mock", "mock")
    predictions = []
    for item in queries:
        question = item.get("query") or item.get("question") or ""
        result = generate_sql_for_question(question, schema_info, indexes or {}, graph or {}, client)
        predictions.append(
            {
                "id": item.get("id", len(predictions)),
                "query": question,
                "predicted_sql": result.get("predicted_sql", ""),
                "latency": result.get("latency", 0.0),
            }
        )
    save_submission(build_submission(config.TEAM_ID, predictions), output_path)
