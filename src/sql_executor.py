"""
执行 SQL 查询并返回结果。

负责人：B
"""

from __future__ import annotations

import sqlite3

try:
    from .sql_checker import is_select_only, normalize_sql
except ImportError:
    from sql_checker import is_select_only, normalize_sql


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
    cleaned = normalize_sql(sql)
    if not is_select_only(cleaned):
        return {"success": False, "rows": [], "columns": [], "error": "only SELECT queries are allowed"}

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(cleaned)
            rows = cursor.fetchall()
            columns = [item[0] for item in cursor.description or []]
            return {
                "success": True,
                "rows": [dict(row) for row in rows],
                "columns": columns,
                "error": None,
            }
    except sqlite3.Error as exc:
        return {"success": False, "rows": [], "columns": [], "error": str(exc)}
