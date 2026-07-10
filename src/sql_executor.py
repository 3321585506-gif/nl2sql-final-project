"""
执行 SQL 查询并返回结果。

负责人：B
"""

def execute_sql(db_path: str, sql: str) -> dict:
    """
    执行 SQL。

    Returns:
        {
            "success": True,
            "rows": [...],
            "columns": [...],
            "error": None
        }
    """
    raise NotImplementedError
