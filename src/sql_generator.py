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


RULE_CONFIDENCE_THRESHOLD = 0.75


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

    # 如果 selected_columns 为空但有 filter，兜底加上常用展示列
    if not selected_columns and filters:
        for default_col in ("品牌", "型号", "型号名称", "价格_元"):
            if default_col in columns_by_table.get(main_table, {}):
                selected_columns.append(default_col)
                if len(selected_columns) >= 3:
                    break

    confidence = 0.0
    if selected_columns:
        confidence += 0.35
    if filters:
        # 比较运算符(> / < / BETWEEN)置信度更高
        has_comparison = any(f.operator in (">", ">=", "<", "<=", "BETWEEN") for f in filters)
        confidence += 0.40 if has_comparison else 0.35
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
    # 1) 精确值匹配（品牌/型号/材质/功能等）
    for column, info in columns.items():
        values = list(info.get("enum_values") or info.get("sample_values") or info.get("samples") or [])
        for value in sorted(values, key=lambda item: -len(str(item))):
            text_value = str(value)
            if text_value and text_value in question and _value_filter_allowed(question, column):
                filters.append(FilterCondition(FieldRef(table, column), "=", value))
                seen_fields.add(column)
                break

    # 2) 数值比较条件（> >= < <= BETWEEN）
    for column in columns:
        if column in seen_fields:
            continue
        num_result = _extract_numeric_condition(question, column)
        if num_result is not None:
            filters.append(FilterCondition(
                FieldRef(table, column), num_result["operator"], num_result["value"]
            ))
            seen_fields.add(column)

    return filters


def _extract_numeric_condition(question: str, column: str) -> dict | None:
    """Extract numeric comparison from question for a given column.

    Returns {"operator": ">=", "value": 3500} or {"operator": "BETWEEN", "value": [5000, 10000]} or None.
    """
    if not _column_mentions(question, column) and not _is_numeric_condition_column(column):
        return None

    import re

    # 找到列名关键词在 question 中的位置，在附近找数字
    label = _column_label(column)
    label_pos = question.find(label) if label in question else question.find(column)
    if label_pos < 0:
        label_pos = 0

    # 在列名附近 30 字符内搜索数字
    search_window = question[max(0, label_pos - 5):label_pos + len(label) + 35]

    # BETWEEN: "X到Y之间" / "X至Y" / "X-Y"
    between_match = re.search(r'(\d+\.?\d*)\s*(?:到|至|[-])\s*(\d+\.?\d*)\s*(?:之间)?', search_window)
    if between_match:
        v1 = float(between_match.group(1))
        v2 = float(between_match.group(2))
        return {"operator": "BETWEEN", "value": [
            int(v1) if v1 == int(v1) else v1,
            int(v2) if v2 == int(v2) else v2,
        ]}

    # 比较: "大于/高于/超过/不小于/不低于/以上" "小于/低于/不超过/不大于/不大于/以下"
    gt_patterns = [
        (r'(?:大于|高于|超过|不小于|不低于|不少于|至少)\s*(\d+\.?\d*)', '>='),
        (r'(\d+\.?\d*)\s*(?:以上|及以上)', '>='),
    ]
    lt_patterns = [
        (r'(?:小于|低于|不超过|不大于|不到)\s*(\d+\.?\d*)', '<='),
        (r'(\d+\.?\d*)\s*(?:以下|及以下)', '<='),
    ]

    for pattern, op in gt_patterns:
        m = re.search(pattern, search_window)
        if m:
            v = float(m.group(1))
            return {"operator": op, "value": int(v) if v == int(v) else v}

    for pattern, op in lt_patterns:
        m = re.search(pattern, search_window)
        if m:
            v = float(m.group(1))
            return {"operator": op, "value": int(v) if v == int(v) else v}

    # 纯数字（兜底 = 匹配）
    digit_match = _find_near_number(question, column)
    if digit_match is not None:
        return {"operator": "=", "value": digit_match}

    return None


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
    """Check if the question mentions this column (by full name or label prefix)."""
    label = _column_label(column)
    if column in question or (len(label) >= 2 and label in question):
        return True
    # 列名各片段是否被提及
    for part in column.split("_"):
        if len(part) >= 2 and part in question:
            return True
    # 常见数值列关键词
    numeric_keywords = (
        "档位", "数量", "级数", "核心数", "线程数", "位数",
        "功率", "容量", "电压", "频率", "转速", "速度",
        "时间", "时长", "年限", "里程", "尺寸", "面积",
        "容积", "重量", "厚度", "长度", "宽度", "高度",
        "价格", "销量", "库存", "噪音", "温度", "风量",
    )
    for token in numeric_keywords:
        if token in column and token in question:
            return True
    return False


def _is_numeric_condition_column(column: str) -> bool:
    """判断列是否可能参与数值比较（大于/小于/范围等）。"""
    # 列名含数量/级/率/功率/容量/时间/速度/尺寸/重量/价格 等 → 数值列
    numeric_tokens = (
        "数量", "级数", "核心数", "线程数", "档位", "位数",
        "功率", "容量", "电压", "电流", "频率", "转速",
        "时间", "时长", "年限", "年份", "月份", "日期",
        "速度", "里程", "距离", "高度", "深度",
        "尺寸", "面积", "容积", "重量", "厚度", "长度", "宽度", "轴距",
        "价格", "金额", "销售额", "销量", "库存", "成本", "毛利",
        "率", "等级", "能效", "分辨率", "像素", "亮度",
        "噪音", "分贝", "温度", "湿度", "风量",
        "倍数", "数量", "个数", "点数",
        "mAh", "Wh", "GHz", "MHz", "Hz", "W", "V", "A",
        "mm", "cm", "m", "kg", "g", "L", "dB", "nit", "ms",
        "℃", "%", "元",
    )
    return any(token in column for token in numeric_tokens)


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
    """Only reject patterns the rule compiler truly cannot handle yet."""
    # 聚合/排序/分组 → rule compiler 暂不支持，走 LLM
    aggregation_markers = [
        "平均", "统计", "总计", "总和", "分组",
        "从低到高", "从高到低", "排序", "排名",
        "前几", "最高", "最低", "最大", "最小",
        "多少款", "多少种", "一共有",
        "成交记录",
    ]
    return not any(marker in question for marker in aggregation_markers)
