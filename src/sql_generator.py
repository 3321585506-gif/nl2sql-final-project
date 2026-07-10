"""
整合检索、Prompt、大模型，生成 SQL，并记录延迟。

负责人：B
"""

def generate_sql_for_question(
    question: str,
    schema_info: dict,
    indexes: dict,
    graph: dict,
    llm_client
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
    raise NotImplementedError
