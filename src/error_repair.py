"""
当 SQL 执行失败时，根据错误信息让大模型修复 SQL。

负责人：B
"""

from __future__ import annotations

try:
    from .prompt_builder import _format_schema_context
    from .sql_checker import extract_sql, is_select_only, normalize_sql
except ImportError:
    from prompt_builder import _format_schema_context
    from sql_checker import extract_sql, is_select_only, normalize_sql


def repair_sql(
    question: str,
    bad_sql: str,
    error_message: str,
    schema_context: dict,
    llm_client,
) -> str:
    """
    根据错误信息修复 SQL。
    最多修复 1-2 次，避免延迟过高。
    """
    prompt = "\n".join(
        [
            "你是一个 SQL 修复助手。请根据错误信息修复 SQL。",
            "要求：只输出修复后的 SQL；只能使用给定表字段；只能生成 SELECT 查询。",
            "",
            f"用户问题：{question}",
            "",
            f"错误 SQL：{bad_sql}",
            "",
            f"数据库错误信息：{error_message}",
            "",
            "可用表结构：",
            _format_schema_context(schema_context or {}),
            "",
            "请输出修复后的 SQL：",
        ]
    )
    repaired = normalize_sql(extract_sql(llm_client.generate(prompt, temperature=0.0, max_tokens=256)))
    if not is_select_only(repaired):
        return normalize_sql(bad_sql)
    return repaired
