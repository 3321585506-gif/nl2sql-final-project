"""
把用户问题、相关 schema、JOIN 路径、示例 SQL 组织成 Prompt。

负责人：B
"""

def build_sql_prompt(
    question: str,
    schema_context: dict,
    join_edges: list[dict],
    intent_info: dict | None = None,
    examples: list[dict] | None = None
) -> str:
    """
    构造用于生成 SQL 的 Prompt。
    """
    raise NotImplementedError
