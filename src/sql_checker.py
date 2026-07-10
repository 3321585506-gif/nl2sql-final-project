"""
检查 SQL 是否安全、是否只包含 SELECT、是否使用不存在的字段。

负责人：B
"""

def extract_sql(text: str) -> str:
    """
    从模型输出中提取 SQL（去掉 markdown 代码块等）。
    """
    raise NotImplementedError


def is_select_only(sql: str) -> bool:
    """
    检查是否只包含 SELECT 查询。
    禁止 DROP、DELETE、UPDATE、INSERT 等操作。
    """
    raise NotImplementedError


def validate_sql_schema(sql: str, schema_info: dict) -> list[str]:
    """
    检查 SQL 中的表名和字段名是否存在。
    返回错误列表。
    """
    raise NotImplementedError


def normalize_sql(sql: str) -> str:
    """
    格式化 SQL，去除多余换行和 markdown 代码块。
    """
    raise NotImplementedError
