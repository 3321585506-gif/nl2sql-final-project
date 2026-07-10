"""
将 SQL 执行结果转成自然语言回答。

负责人：B
"""

from __future__ import annotations


def polish_answer(question: str, sql_result: dict) -> str:
    """
    将查询结果转成自然语言回答。
    """
    if not sql_result.get("success"):
        return f"查询失败：{sql_result.get('error') or '未知错误'}"

    rows = sql_result.get("rows") or []
    columns = sql_result.get("columns") or []
    if not rows:
        return "未查询到符合条件的商品。"

    if len(rows) == 1:
        row = rows[0]
        values = _row_values(row, columns)
        if len(values) == 1:
            result = next(iter(values.values())) if isinstance(values, dict) else values[0]
            return f"查询结果为：{result}。"
        return "查询到 1 条结果：" + "，".join(f"{key}为{value}" for key, value in values.items()) + "。"

    preview = rows[:5]
    items = []
    for row in preview:
        values = _row_values(row, columns)
        if isinstance(values, dict):
            items.append("，".join(f"{key}为{value}" for key, value in values.items()))
        else:
            items.append(str(values))
    suffix = "；".join(items)
    more = f"等共 {len(rows)} 条结果" if len(rows) > len(preview) else f"共 {len(rows)} 条结果"
    return f"查询到{more}：{suffix}。"


def _row_values(row: object, columns: list[str]) -> dict | list:
    if isinstance(row, dict):
        return row
    if isinstance(row, (list, tuple)):
        if len(row) == 1:
            return [row[0]]
        return {columns[index] if index < len(columns) else str(index): value for index, value in enumerate(row)}
    return [row]
