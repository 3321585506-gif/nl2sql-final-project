"""
对自然语言问题进行预处理，抽取品牌、型号、数值条件、排序条件、聚合意图等。

负责人：A + B
"""

from __future__ import annotations

import re

try:
    from .query_ir import FieldRef, FilterCondition, QueryIR
except ImportError:
    from query_ir import FieldRef, FilterCondition, QueryIR


def normalize_text(text: str) -> str:
    """
    统一中英文符号、去除多余空格、大小写归一化。
    """
    value = re.sub(r"\s+", " ", (text or "").strip())
    value = value.replace("（", "(").replace("）", ")")
    value = value.replace("，", ",").replace("。", ".")
    value = value.replace("：", ":").replace("；", ";")
    return value


def normalize_question(question: str) -> str:
    """Alias kept for the V2 query processor interface."""
    return normalize_text(question)


def extract_numbers_and_units(question: str) -> list[dict]:
    """
    抽取数值和单位，例如 5000mAh、95%、5000到10000元。
    """
    results: list[dict] = []
    text = normalize_text(question)
    range_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(?:到|至|-)\s*(\d+(?:\.\d+)?)\s*([A-Za-z%_\u4e00-\u9fff]*)")
    for match in range_pattern.finditer(text):
        results.append(
            {
                "type": "range",
                "value": [_number_value(match.group(1)), _number_value(match.group(2))],
                "unit": match.group(3) or None,
                "text": match.group(0),
            }
        )
    single_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*([A-Za-z%_\u4e00-\u9fff]*)")
    for match in single_pattern.finditer(text):
        if any(match.group(0) in item["text"] for item in results):
            continue
        results.append(
            {
                "type": "number",
                "value": _number_value(match.group(1)),
                "unit": match.group(2) or None,
                "text": match.group(0),
            }
        )
    return results


def detect_query_intent(question: str) -> dict:
    """
    检测查询意图。

    Returns:
        {
            "need_aggregation": True,
            "aggregation_type": "AVG",
            "need_group_by": True,
            "need_order_by": True,
            "filters": [...]
        }
    """
    text = normalize_text(question)
    aggregation = detect_aggregation(text)
    return {
        "need_aggregation": aggregation is not None,
        "aggregation_type": aggregation.get("function") if aggregation else None,
        "need_group_by": "按" in text and "统计" in text,
        "need_order_by": any(word in text for word in ["排序", "从低到高", "从高到低", "最高", "最低", "排名"]),
        "limit": detect_limit(text),
        "numbers": extract_numbers_and_units(text),
    }


def extract_entities(question: str, entity_indexes: dict, schema_catalog: dict) -> dict:
    """Extract exact brand/model mentions from entity indexes."""
    text = normalize_text(question)
    lower_text = text.lower()
    model_hit = _longest_index_hit(lower_text, entity_indexes.get("model_index", {}))
    brand_hit = _longest_index_hit(lower_text, entity_indexes.get("brand_index", {}))
    return {
        "brand": brand_hit,
        "model": model_hit,
        "numeric_values": extract_numbers_and_units(text),
    }


def detect_aggregation(question: str) -> dict | None:
    text = normalize_text(question)
    if any(word in text for word in ["一共有多少", "多少款", "数量", "总数"]):
        return {"function": "COUNT", "field": None}
    mapping = [
        ("平均", "AVG"),
        ("最高", "MAX"),
        ("最大", "MAX"),
        ("最低", "MIN"),
        ("最小", "MIN"),
        ("总", "SUM"),
    ]
    for word, function in mapping:
        if word in text:
            return {"function": function}
    return None


def detect_limit(question: str) -> int | None:
    text = normalize_text(question)
    match = re.search(r"(?:前|top\s*)(\d+)", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    chinese_limits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}
    for key, value in chinese_limits.items():
        if f"前{key}" in text:
            return value
    return None


def parse_query_to_ir(question: str, artifacts: dict) -> QueryIR:
    """
    Rule-first parser for high-confidence common templates.

    V2 first stage focuses on single-product attribute queries:
    model exact hit + selected fields + single table.
    """
    schema_catalog = artifacts.get("schema_catalog") or {}
    entity_indexes = artifacts.get("entity_indexes") or {}
    entities = extract_entities(question, entity_indexes, schema_catalog)
    model = entities.get("model")
    table = None
    model_field = None
    model_value = None
    if model:
        model_ref = model["refs"][0]
        table = model_ref["table"]
        model_field = model_ref["field"]
        model_value = model_ref["value"]
    else:
        table = _infer_table(question, schema_catalog)
        model_value = _extract_model_literal(question)
        model_field = _model_field_for_table(schema_catalog, table) if table else None

    if not table or not model_field or not model_value:
        return QueryIR(confidence=0.0, source="rule")

    columns = (schema_catalog.get("tables", {}).get(table, {}).get("columns", {}))
    if not columns:
        return QueryIR(confidence=0.0, source="rule")

    select_columns = _select_columns(question, columns)
    select_columns = [column for column in select_columns if column != model_field]
    if not select_columns:
        return QueryIR(confidence=0.0, source="rule")

    filters = [FilterCondition(FieldRef(table, model_field), "=", model_value)]
    confidence = min(
        1.0,
        0.4
        + 0.35
        + (0.2 if len(select_columns) <= 8 else 0.1)
        + (0.05 if table else 0.0),
    )
    return QueryIR(
        select_fields=[FieldRef(table, column) for column in select_columns],
        filters=filters,
        required_tables=[table],
        confidence=confidence,
        source="rule",
    )


def _select_columns(question: str, columns: dict) -> list[str]:
    selected_positions: dict[str, int] = {}
    for column, info in columns.items():
        role = info.get("role")
        if role == "model":
            continue
        aliases = [column, _column_label(column)] + list(info.get("aliases") or [])
        positions = [question.find(alias) for alias in aliases if alias and alias in question]
        if positions:
            selected_positions[column] = min(positions)

    selected = [
        column
        for column, _ in sorted(selected_positions.items(), key=lambda item: (item[1], item[0]))
    ]
    if not selected and "电池" in question and "类型" in question:
        selected.extend(column for column in columns if "电池" in column and "类型" in column)
    if not selected and "散热" in question:
        selected.extend(column for column in columns if "散热" in column)
    selected = _dedupe(selected)
    if "散热器类型" in selected and "散热方式" in selected:
        selected.remove("散热方式")
    return selected


def _infer_table(question: str, schema_catalog: dict) -> str | None:
    category_map = [
        ("空调", "air_conditioner"),
        ("电动车", "electric_vehicle"),
        ("相机", "digital_camera"),
        ("耳机", "headphones"),
        ("台式机", "desktop_computer"),
        ("电脑", "desktop_computer"),
        ("笔记本", "computer_join_main"),
    ]
    for keyword, table in category_map:
        if keyword in question and table in (schema_catalog.get("tables") or {}):
            return table

    scores: dict[str, int] = {}
    for table, table_info in (schema_catalog.get("tables") or {}).items():
        columns = table_info.get("columns", {})
        if _select_columns(question, columns):
            scores[table] = scores.get(table, 0) + 3
        for column, info in columns.items():
            if info.get("role") == "brand":
                for value in info.get("sample_values") or []:
                    if str(value) and str(value) in question:
                        scores[table] = scores.get(table, 0) + 2
    if not scores:
        return None
    return max(scores.items(), key=lambda item: item[1])[0]


def _model_field_for_table(schema_catalog: dict, table: str | None) -> str | None:
    if not table:
        return None
    columns = (schema_catalog.get("tables", {}).get(table, {}).get("columns", {}))
    for preferred in ("型号", "型号名称"):
        if preferred in columns:
            return preferred
    for column, info in columns.items():
        if info.get("role") == "model":
            return column
    return None


def _extract_model_literal(question: str) -> str | None:
    patterns = [
        r"(KFR[A-Za-z0-9/+._()%-]+)",
        r"(\d{3,4}-[A-Za-z0-9]+)",
        r"([\u4e00-\u9fff]{1,4}[A-Za-z]\d[A-Za-z0-9+-]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            value = match.group(1).rstrip("这款这个的？?，,。")
            if len(value) >= 3:
                return value
    return None


def _longest_index_hit(lower_text: str, index: dict) -> dict | None:
    for value in sorted(index.keys(), key=lambda item: (-len(item), item)):
        if value and value in lower_text:
            return {"value": index[value][0]["value"], "key": value, "refs": index[value]}
    return None


def _column_label(column: str) -> str:
    return column.split("_", 1)[0]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _number_value(raw: str) -> int | float:
    value = float(raw)
    return int(value) if value.is_integer() else value


# ========== 等级/级别词 → 数值映射 ==========

# 中文等级词 → 数值
_LEVEL_MAP: dict[str, int] = {
    "一级": 1, "二级": 2, "三级": 3, "四级": 4, "五级": 5,
    "六級": 6, "七级": 7, "八级": 8, "九级": 9,
    "1级": 1, "2级": 2, "3级": 3, "4级": 4, "5级": 5,
    "Ⅰ级": 1, "Ⅱ级": 2, "Ⅲ级": 3, "Ⅳ级": 4, "Ⅴ级": 5,
}
# 等级词对应的列名候选
_LEVEL_COLUMNS: list[str] = [
    "能效等级", "能效级别", "能耗等级", "防水防尘等级", "防护等级",
    "防水等级", "防尘防水等级", "噪音等级", "防腐等级",
]


def extract_level_value(question: str) -> dict | None:
    """
    从问题中提取等级描述词，映射为数值。

    "一级能效" → {"value": 1, "columns": ["能效等级", "能效级别", ...]}
    """
    for word, value in sorted(_LEVEL_MAP.items(), key=lambda x: -len(x[0])):
        if word in question:
            return {"value": value, "word": word, "columns": list(_LEVEL_COLUMNS)}
    return None
