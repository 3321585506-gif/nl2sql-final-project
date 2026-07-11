"""
整合检索、Prompt、大模型，生成 SQL，并记录延迟。

负责人：B
"""

from __future__ import annotations

import time

try:
    from .query_ir import FieldRef, FilterCondition, QueryIR
    from .prompt_builder import build_sql_prompt
    from .sql_compiler import compile_query_ir
    from .sql_checker import extract_sql, is_select_only, normalize_sql, validate_sql_schema
except ImportError:
    from query_ir import FieldRef, FilterCondition, QueryIR
    from prompt_builder import build_sql_prompt
    from sql_compiler import compile_query_ir
    from sql_checker import extract_sql, is_select_only, normalize_sql, validate_sql_schema


RULE_CONFIDENCE_THRESHOLD = 0.85


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
    stage_timings: dict[str, float] = {}

    stage_start = time.perf_counter()
    intent_info = _detect_intent(question)
    stage_timings["preprocess_ms"] = _elapsed_ms(stage_start)

    stage_start = time.perf_counter()
    schema_context = _retrieve_schema_context(question, schema_info, indexes)
    stage_timings["retrieval_ms"] = _elapsed_ms(stage_start)

    stage_start = time.perf_counter()
    join_edges = _find_join_edges(graph, schema_context.get("tables", []))
    stage_timings["join_ms"] = _elapsed_ms(stage_start)

    stage_start = time.perf_counter()
    parser_result = _parse_artifact_query_to_ir(question, indexes or {})
    if parser_result.confidence < RULE_CONFIDENCE_THRESHOLD:
        parser_result = _parse_rule_query_to_ir(question, schema_context, schema_info)
    route = route_query(question, parser_result, (indexes or {}).get("cache", {}))
    stage_timings["parse_ms"] = _elapsed_ms(stage_start)

    error = None
    raw_output = ""
    predicted_sql = ""

    if route == "cache":
        predicted_sql = (indexes or {}).get("cache", {}).get(question, "")
        stage_timings["compile_ms"] = 0.0
        stage_timings["llm_ms"] = 0.0

    if route == "rule":
        try:
            stage_start = time.perf_counter()
            predicted_sql = compile_query_ir(parser_result, join_edges)
            stage_timings["compile_ms"] = _elapsed_ms(stage_start)
            stage_timings["llm_ms"] = 0.0
        except Exception as exc:
            error = f"rule route failed: {exc}"
            route = "llm"

    if route == "llm":
        stage_timings.setdefault("compile_ms", 0.0)
        stage_start = time.perf_counter()
        prompt = build_sql_prompt(
            question=question,
            schema_context=schema_context,
            join_edges=join_edges,
            intent_info=intent_info,
            examples=(indexes or {}).get("examples", []),
        )
        stage_timings["prompt_ms"] = _elapsed_ms(stage_start)

        try:
            stage_start = time.perf_counter()
            raw_output = llm_client.generate(prompt, temperature=0.0, max_tokens=1024)
            stage_timings["llm_ms"] = _elapsed_ms(stage_start)
            predicted_sql = normalize_sql(extract_sql(raw_output))
        except Exception as exc:
            stage_timings["llm_ms"] = _elapsed_ms(stage_start)
            error = str(exc)
            predicted_sql = _fallback_sql(schema_context)
            route = "fallback"

    stage_start = time.perf_counter()
    predicted_sql = normalize_sql(predicted_sql)
    if not is_select_only(predicted_sql):
        error = error or "generated SQL is not a safe SELECT query"
    schema_errors = validate_sql_schema(predicted_sql, schema_info)
    if schema_errors:
        error = "; ".join(schema_errors)
    stage_timings["validation_ms"] = _elapsed_ms(stage_start)

    latency = time.perf_counter() - start
    stage_timings["total_ms"] = round(latency * 1000, 3)
    return {
        "question": question,
        "predicted_sql": predicted_sql,
        "latency": latency,
        "schema_context": schema_context,
        "join_edges": join_edges,
        "intent_info": intent_info,
        "raw_output": raw_output,
        "error": error,
        "route": route,
        "confidence": parser_result.confidence,
        "stage_timings": stage_timings,
    }


def route_query(question: str, parser_result: QueryIR, cache: dict | None) -> str:
    """Return cache/rule/llm according to cache and parser confidence."""
    if cache and question in cache:
        return "cache"
    if not _is_rule_supported_question(question):
        return "llm"
    if parser_result.confidence >= RULE_CONFIDENCE_THRESHOLD:
        return "rule"
    return "llm"


def _parse_artifact_query_to_ir(question: str, indexes: dict) -> QueryIR:
    if not indexes.get("schema_catalog") or not indexes.get("entity_indexes"):
        return QueryIR(confidence=0.0, source="rule")
    try:
        from .query_processor import parse_query_to_ir
    except ImportError:
        from query_processor import parse_query_to_ir
    try:
        return parse_query_to_ir(question, indexes)
    except Exception:
        return QueryIR(confidence=0.0, source="rule")


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


def _parse_rule_query_to_ir(question: str, schema_context: dict, schema_info: dict | None = None) -> QueryIR:
    fields = schema_context.get("fields") or []
    table_counts: dict[str, int] = {}
    columns_by_table: dict[str, dict[str, dict]] = {}
    for field in fields:
        table = str(field.get("table") or field.get("table_name") or "").strip()
        column = str(field.get("field") or field.get("name") or field.get("column") or "").strip()
        if not table or not column:
            continue
        enriched = dict(field)
        if not (enriched.get("sample_values") or enriched.get("samples")):
            samples = _schema_sample_values(schema_info or {}, table, column)
            if samples:
                enriched["sample_values"] = samples
        table_counts[table] = table_counts.get(table, 0) + 1
        columns_by_table.setdefault(table, {})[column] = enriched

    if not table_counts:
        return QueryIR(confidence=0.0, source="rule")

    main_table = max(table_counts.items(), key=lambda item: item[1])[0]
    filters = _filters_from_question(question, main_table, columns_by_table.get(main_table, {}))
    filter_columns = {item.field.column for item in filters}
    selected_columns = [
        column
        for column in _select_columns_from_question(question, columns_by_table.get(main_table, {}))
        if column not in filter_columns
    ]

    confidence = 0.0
    if selected_columns:
        confidence += 0.35
    if filters:
        confidence += 0.35
    if len(table_counts) == 1:
        confidence += 0.2
    elif _is_dominant_table(main_table, table_counts):
        confidence += 0.15
    if len(selected_columns) >= 2:
        confidence += 0.1

    return QueryIR(
        select_fields=[FieldRef(main_table, column) for column in selected_columns],
        filters=filters,
        required_tables=[main_table],
        confidence=min(confidence, 0.95),
        source="rule",
    )


def _select_columns_from_question(question: str, columns: dict[str, dict]) -> list[str]:
    selected: list[str] = []
    for column in columns:
        if column and (column in question or _column_label(column) in question):
            selected.append(column)
    if selected:
        return selected

    for default in ("品牌", "型号", "型号名称"):
        if default in columns:
            selected.append(default)
    return selected


def _column_label(column: str) -> str:
    return column.split("_", 1)[0]


def _filters_from_question(question: str, table: str, columns: dict[str, dict]) -> list[FilterCondition]:
    filters: list[FilterCondition] = []
    seen_fields: set[str] = set()
    for column, info in columns.items():
        values = list(info.get("enum_values") or info.get("sample_values") or info.get("samples") or [])
        for value in sorted(values, key=lambda item: -len(str(item))):
            text_value = str(value)
            if text_value and text_value in question and _value_filter_allowed(question, column):
                filters.append(FilterCondition(FieldRef(table, column), "=", value))
                seen_fields.add(column)
                break
    for column in columns:
        if column in seen_fields:
            continue
        numeric_value = _numeric_value_for_column(question, column)
        if numeric_value is not None:
            filters.append(FilterCondition(FieldRef(table, column), "=", numeric_value))
    return filters


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def _schema_sample_values(schema_info: dict, table: str, column: str) -> list:
    table_info = (schema_info or {}).get("tables", {}).get(table, {})
    for item in table_info.get("columns", []):
        if isinstance(item, dict) and item.get("name") == column:
            return list(item.get("sample_values") or [])
    return []


def _is_dominant_table(main_table: str, table_counts: dict[str, int]) -> bool:
    counts = sorted(table_counts.items(), key=lambda item: item[1], reverse=True)
    if not counts or counts[0][0] != main_table or len(counts) == 1:
        return True
    return counts[0][1] >= max(counts[1][1] * 2, counts[1][1] + 3)


def _numeric_value_for_column(question: str, column: str) -> int | float | None:
    if not _column_mentions(question, column):
        return None
    if not _is_numeric_condition_column(column):
        return None
    digit_match = _find_near_number(question, column)
    if digit_match is not None:
        return digit_match
    chinese_numbers = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    for char, value in chinese_numbers.items():
        if f"{char}个" in question or f"{char}档" in question or f"{char}级" in question:
            return value
    return None


def _value_filter_allowed(question: str, column: str) -> bool:
    if column in {"品牌", "品牌名称", "型号", "型号名称", "SKU编码"}:
        return True
    return _column_mentions(question, column)


def _column_mentions(question: str, column: str) -> bool:
    label = _column_label(column)
    if column in question or (len(label) >= 2 and label in question):
        return True
    for token in ("档位", "数量", "级数", "核心数", "线程数"):
        if token in column and token[:2] in question:
            return True
    return False


def _is_numeric_condition_column(column: str) -> bool:
    return any(token in column for token in ("数量", "级数", "核心数", "线程数", "档位"))


def _find_near_number(question: str, column: str) -> int | float | None:
    import re

    if column in question:
        pattern = re.compile(rf"{re.escape(column)}\D{{0,6}}(\d+(?:\.\d+)?)")
    else:
        pattern = re.compile(r"(\d+(?:\.\d+)?)\D{0,4}(?:个)?(?:档位|档|级|核|线程)")
    match = pattern.search(question)
    if not match:
        return None
    value = float(match.group(1))
    return int(value) if value.is_integer() else value


def _is_rule_supported_question(question: str) -> bool:
    unsupported_markers = [
        "至少",
        "不低于",
        "不超过",
        "之间",
        "以上",
        "以下",
        "从低到高",
        "从高到低",
        "排序",
        "排名",
        "前",
        "最低",
        "最高的",
        "最大",
        "最小",
        "平均",
        "统计",
        "成交记录",
        "目前在售",
        "还在售",
    ]
    return not any(marker in question for marker in unsupported_markers)
