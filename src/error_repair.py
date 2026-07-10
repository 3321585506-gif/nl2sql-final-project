"""
当 SQL 执行失败时，根据错误信息让大模型修复 SQL。

负责人：B
"""

def repair_sql(
    question: str,
    bad_sql: str,
    error_message: str,
    schema_context: dict,
    llm_client
) -> str:
    """
    根据错误信息修复 SQL。
    最多修复 1-2 次，避免延迟过高。
    """
    raise NotImplementedError
