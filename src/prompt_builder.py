"""
把用户问题、相关 schema、JOIN 路径、示例 SQL 组织成 Prompt。

负责人：B
"""

from __future__ import annotations

import json


def build_sql_prompt(
    question: str,
    schema_context: dict,
    join_edges: list[dict],
    intent_info: dict | None = None,
    examples: list[dict] | None = None,
) -> str:
    """
    构造用于生成 SQL 的 Prompt。
    """
    if not question or not question.strip():
        raise ValueError("question must not be empty")

    schema_text = _format_schema_context(schema_context or {})
    join_text = _format_join_edges(join_edges or [])
    intent_text = _format_json(intent_info or {})
    examples_text = _format_examples(examples or [])

    return "\n".join(
        [
            "你是一个 NL2SQL 系统。请根据用户问题和数据库结构生成一条可执行 SQL。",
            "",
            "要求：",
            "1. 只输出 SQL，不要输出解释、Markdown 或代码块。",
            "2. 只能使用下方给定的表和字段。",
            "3. 如果需要多表查询，请优先使用给定 JOIN 条件。",
            "4. SQL 必须是 SELECT 查询，可以使用 WITH，但禁止 INSERT、UPDATE、DELETE、DROP、ALTER、CREATE。",
            "5. 字符串条件使用单引号。",
            "6. 不要编造不存在的表或字段。",
            "7. 如需限制展示数量，可使用 LIMIT。",
            "",
            "重要提醒（必须遵守）：",
            "8. 所有列名均为中文（可能含下划线和单位后缀，如 电池容量_mAh、制冷量_W、价格_元、机身重量_kg、年耗电量_kWh）。",
            "9. 必须使用完整的列名，不可截断后缀。例如「年耗电量_kWh」不可写成「年耗电量」。",
            "10. 禁止使用英文列名（如 brand/model/price 等），数据库中不存在英文列名。",
            "11. 数值比较时，注意区分 > 和 >=。如「以上」「大于」「超过」「高于」通常对应 >（不含等于），「不小于」「不低于」「至少」对应 >=（含等于）。",
            "12. 查询具体型号时，应使用「型号」或「型号名称」列，不要使用「产品类型」「空调类型」等类别列。",
            "",
            "用户问题：",
            question.strip(),
            "",
            "相关表结构：",
            schema_text,
            "",
            "可用 JOIN 条件：",
            join_text,
            "",
            "识别出的查询意图：",
            intent_text,
            "",
            "示例：",
            examples_text,
            "",
            "请输出 SQL：",
        ]
    )


def _format_schema_context(schema_context: dict) -> str:
    fields = schema_context.get("fields") or []
    if fields:
        grouped: dict[str, list[str]] = {}
        for field in fields:
            table = str(field.get("table") or field.get("table_name") or "").strip()
            name = str(field.get("field") or field.get("name") or field.get("column") or "").strip()
            if not table or not name:
                continue
            column_type = field.get("type") or field.get("column_type") or ""
            desc = field.get("description") or ""
            sample_values = field.get("sample_values") or field.get("samples") or []
            extras = []
            if column_type:
                extras.append(str(column_type))
            if desc:
                extras.append(str(desc))
            if sample_values:
                extras.append("示例值: " + ", ".join(map(str, sample_values[:3])))
            suffix = f" ({'; '.join(extras)})" if extras else ""
            grouped.setdefault(table, []).append(f"- {name}{suffix}")
        if grouped:
            return "\n".join([f"表 {table}:\n" + "\n".join(cols) for table, cols in grouped.items()])

    tables = schema_context.get("tables") or {}
    if isinstance(tables, dict):
        lines = []
        for table, info in tables.items():
            columns = info.get("columns", []) if isinstance(info, dict) else []
            lines.append(f"表 {table}:")
            for column in columns:
                if isinstance(column, dict):
                    name = column.get("name") or column.get("field") or column.get("column")
                    column_type = column.get("type") or ""
                    desc = column.get("description") or ""
                    lines.append(f"- {name} ({column_type}; {desc})".rstrip(" ;()"))
                else:
                    lines.append(f"- {column}")
        if lines:
            return "\n".join(lines)

    return _format_json(schema_context) if schema_context else "无"


def _format_join_edges(join_edges: list[dict]) -> str:
    if not join_edges:
        return "无"
    lines = []
    for edge in join_edges:
        source = edge.get("from") or edge.get("source") or edge.get("left")
        target = edge.get("to") or edge.get("target") or edge.get("right")
        on_clause = edge.get("on") or edge.get("condition")
        if on_clause:
            lines.append(f"- {source} JOIN {target} ON {on_clause}")
        else:
            lines.append(f"- {edge}")
    return "\n".join(lines)


def _format_examples(examples: list[dict]) -> str:
    if not examples:
        return "无"
    chunks = []
    for example in examples:
        query = example.get("query") or example.get("question") or ""
        sql = example.get("sql") or example.get("predicted_sql") or ""
        chunks.append(f"问题：{query}\nSQL：{sql}".strip())
    return "\n\n".join(chunks)


def _format_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
