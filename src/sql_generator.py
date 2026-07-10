"""
整合检索、Prompt、大模型，生成 SQL，并记录延迟。

负责人：B
"""

from __future__ import annotations

import time

try:
    from .prompt_builder import build_sql_prompt
    from .sql_checker import extract_sql, is_select_only, normalize_sql, validate_sql_schema
except ImportError:
    from prompt_builder import build_sql_prompt
    from sql_checker import extract_sql, is_select_only, normalize_sql, validate_sql_schema


def generate_sql_for_question(
    question: str,
    schema_info: dict,
    indexes: dict,
    graph: dict,
    llm_client,
) -> dict:
    """
    输入自然语言问题，输出 SQL 和延迟。

    Returns:
        {
            "question": "...",
            "predicted_sql": "SELECT ...",
            "latency": 1.23,
            "schema_context": {...},
            "join_edges": [...]
        }
    """
    start = time.perf_counter()
    intent_info = _detect_intent(question)
    schema_context = _retrieve_schema_context(question, schema_info, indexes)
    join_edges = _find_join_edges(graph, schema_context.get("tables", []))
    prompt = build_sql_prompt(
        question=question,
        schema_context=schema_context,
        join_edges=join_edges,
        intent_info=intent_info,
        examples=(indexes or {}).get("examples", []),
    )

    error = None
    raw_output = ""
    try:
        raw_output = llm_client.generate(prompt, temperature=0.0, max_tokens=256)
        predicted_sql = normalize_sql(extract_sql(raw_output))
        if not is_select_only(predicted_sql):
            error = "generated SQL is not a safe SELECT query"
        schema_errors = validate_sql_schema(predicted_sql, schema_info)
        if schema_errors:
            error = "; ".join(schema_errors)
    except Exception as exc:
        error = str(exc)
        predicted_sql = _fallback_sql(schema_context)

    latency = time.perf_counter() - start
    return {
        "question": question,
        "predicted_sql": predicted_sql,
        "latency": latency,
        "schema_context": schema_context,
        "join_edges": join_edges,
        "intent_info": intent_info,
        "raw_output": raw_output,
        "error": error,
    }


def _detect_intent(question: str) -> dict:
    try:
        from .query_processor import detect_query_intent
    except ImportError:
        try:
            from query_processor import detect_query_intent
        except ImportError:
            return {}
    try:
        return detect_query_intent(question)
    except NotImplementedError:
        return {}


def _retrieve_schema_context(question: str, schema_info: dict, indexes: dict) -> dict:
    indexes = indexes or {}
    try:
        from .retriever import retrieve_schema_context
    except ImportError:
        try:
            from retriever import retrieve_schema_context
        except ImportError:
            return _fallback_schema_context(schema_info)
    try:
        return retrieve_schema_context(
            question=question,
            schema_info=schema_info,
            alias_map=indexes.get("alias_map", {}),
            inverted_index=indexes.get("inverted_index", {}),
            top_k_fields=int(indexes.get("top_k_fields", 20)),
        )
    except NotImplementedError:
        return _fallback_schema_context(schema_info)


def _find_join_edges(graph: dict, tables: list[str]) -> list[dict]:
    if not graph or len(tables) < 2:
        return []
    try:
        from .schema_graph import find_join_edges_for_tables
    except ImportError:
        try:
            from schema_graph import find_join_edges_for_tables
        except ImportError:
            return []
    try:
        return find_join_edges_for_tables(graph, tables)
    except NotImplementedError:
        return []


def _fallback_schema_context(schema_info: dict, max_fields: int = 20) -> dict:
    fields = []
    tables = []
    for table, info in (schema_info or {}).get("tables", {}).items():
        tables.append(table)
        columns = info.get("columns", []) if isinstance(info, dict) else []
        for column in columns:
            if isinstance(column, dict):
                field = dict(column)
                field.setdefault("field", field.get("name"))
                field["table"] = table
            else:
                field = {"table": table, "field": str(column), "name": str(column)}
            fields.append(field)
            if len(fields) >= max_fields:
                return {"tables": tables, "fields": fields, "matched_keywords": []}
    return {"tables": tables, "fields": fields, "matched_keywords": []}


def _fallback_sql(schema_context: dict) -> str:
    tables = schema_context.get("tables") or []
    if not tables:
        return ""
    return f"SELECT * FROM {tables[0]} LIMIT 20;"
