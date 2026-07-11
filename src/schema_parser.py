"""
解析数据库表结构，生成给检索模块和 PromptBuilder 使用的 schema_info。

负责人：A

数据来源：
- SQLite 数据库（PRAGMA table_info）
- DDL 文件（补充字段的中文描述）

输出 schema_info 结构：
{
    "tables": {
        "table_name": {
            "columns": [
                {
                    "name": "column_name",
                    "type": "TEXT",
                    "description": "",
                    "sample_values": ["v1", "v2"]
                }
            ]
        }
    }
}
"""

import re
import sqlite3
from pathlib import Path


# ========== Schema 解析 ==========

def parse_sqlite_schema(db_path: str, ddl_path: str | None = None) -> dict:
    """
    解析 SQLite 数据库结构，生成 schema_info。

    步骤：
    1. 连接 SQLite，用 PRAGMA table_info 获取每张表的列名和类型
    2. 如果提供了 DDL 文件，从中提取额外的注释/描述信息
    3. 每列抽取少量样例值

    Args:
        db_path: SQLite 数据库路径
        ddl_path: DDL 文件路径（可选），用于补充字段说明

    Returns:
        schema_info = {
            "tables": {
                "table_name": {
                    "columns": [
                        {"name": "...", "type": "...", "description": "", "sample_values": [...]}
                    ]
                }
            }
        }
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = [row[0] for row in cursor.fetchall()]

    # 尝试从 DDL 中提取注释（如果有）
    ddl_comments = {}
    if ddl_path:
        ddl_comments = _parse_ddl_comments(ddl_path)

    schema_info = {"tables": {}}

    for table_name in table_names:
        # PRAGMA table_info 获取列信息
        cursor.execute(f"PRAGMA table_info('{table_name}')")
        pragma_rows = cursor.fetchall()
        # 返回格式: (cid, name, type, notnull, dflt_value, pk)

        columns = []
        for row in pragma_rows:
            col_name = row[1]
            col_type = row[2] if row[2] else "TEXT"  # 无类型默认 TEXT

            # 从 DDL 中查找描述
            description = ddl_comments.get(table_name, {}).get(col_name, "")

            # 抽取样例值（只取非空值）
            sample_values = _safe_sample(cursor, table_name, col_name)

            columns.append({
                "name": col_name,
                "type": col_type,
                "description": description,
                "sample_values": sample_values,
            })

        schema_info["tables"][table_name] = {"columns": columns}

    conn.close()

    # 打印统计
    total_cols = sum(len(t["columns"]) for t in schema_info["tables"].values())
    print(f"Schema parsed: {len(table_names)} tables, {total_cols} columns total")
    for name, info in schema_info["tables"].items():
        col_names = [c["name"] for c in info["columns"][:5]]
        print(f"  [{name}] {len(info['columns'])} cols: {col_names}...")

    return schema_info


def collect_sample_values(db_path: str, table: str, column: str, limit: int = 5) -> list:
    """
    从数据库中抽取某字段的非空、去重样例值。

    Args:
        db_path: SQLite 数据库路径
        table: 表名
        column: 列名
        limit: 最多返回条数

    Returns:
        样例值列表（字符串形式）
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    result = _safe_sample(cursor, table, column, limit)
    conn.close()
    return result


def build_schema_catalog(db_path: str, sample_limit: int = 20) -> dict:
    """
    Build a richer, JSON-serializable schema catalog.

    The catalog is intended for entity extraction, value indexes, and prompt
    construction. It should be built during preprocessing, not once per query.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = [row[0] for row in cursor.fetchall()]

    catalog = {"tables": {}}
    for table_name in table_names:
        cursor.execute(f"PRAGMA table_info({_quote_sqlite_literal(table_name)})")
        columns = {}
        for row in cursor.fetchall():
            column_name = row[1]
            column_type = row[2] or "TEXT"
            profile = collect_column_profile(
                db_path=db_path,
                table=table_name,
                column=column_name,
                sample_limit=sample_limit,
                _cursor=cursor,
            )
            columns[column_name] = {
                "type": column_type,
                "aliases": _default_column_aliases(column_name),
                "sample_values": profile["sample_values"],
                "enum_values": profile["enum_values"],
                "distinct_count": profile["distinct_count"],
                "min_value": profile["min_value"],
                "max_value": profile["max_value"],
                "unit": _infer_unit(column_name),
                "role": _infer_column_role(column_name),
            }
        catalog["tables"][table_name] = {"columns": columns}
    conn.close()
    return catalog


def collect_column_profile(
    db_path: str,
    table: str,
    column: str,
    sample_limit: int = 20,
    _cursor=None,
) -> dict:
    """
    Collect distinct count, sample values, enum values, and numeric range.

    _cursor is an internal hook used by build_schema_catalog to reuse the same
    connection while preserving the public function signature.
    """
    owns_connection = _cursor is None
    conn = None
    cursor = _cursor
    if cursor is None:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

    profile = {
        "distinct_count": 0,
        "sample_values": [],
        "enum_values": [],
        "min_value": None,
        "max_value": None,
    }
    table_sql = _quote_identifier(table)
    column_sql = _quote_identifier(column)

    try:
        cursor.execute(
            f"SELECT COUNT(DISTINCT {column_sql}) FROM {table_sql} "
            f"WHERE {column_sql} IS NOT NULL"
        )
        profile["distinct_count"] = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            f"SELECT DISTINCT {column_sql} FROM {table_sql} "
            f"WHERE {column_sql} IS NOT NULL LIMIT {int(sample_limit)}"
        )
        values = [row[0] for row in cursor.fetchall() if row[0] is not None]
        profile["sample_values"] = [_json_safe_value(value) for value in values]
        if 0 < profile["distinct_count"] <= sample_limit:
            profile["enum_values"] = list(profile["sample_values"])

        cursor.execute(
            f"SELECT MIN(CAST({column_sql} AS REAL)), MAX(CAST({column_sql} AS REAL)) "
            f"FROM {table_sql} WHERE {column_sql} IS NOT NULL "
            f"AND (TRIM(CAST({column_sql} AS TEXT)) GLOB '-[0-9]*' "
            f"OR TRIM(CAST({column_sql} AS TEXT)) GLOB '[0-9]*')"
        )
        min_value, max_value = cursor.fetchone()
        if min_value is not None and max_value is not None:
            profile["min_value"] = float(min_value)
            profile["max_value"] = float(max_value)
    except Exception:
        pass
    finally:
        if owns_connection and conn is not None:
            conn.close()

    return profile


# ========== 内部辅助函数 ==========

def _safe_sample(cursor, table: str, column: str, limit: int = 5) -> list:
    """
    安全地抽取样例值：处理 NULL、特殊字符、列名引号等问题。
    """
    try:
        # 使用双引号包裹列名，防止中文列名/特殊字符问题
        sql = f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT {limit}'
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [str(r[0]) for r in rows if r[0] is not None]
    except Exception:
        return []


def _quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _quote_sqlite_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _json_safe_value(value):
    if isinstance(value, (int, float)) or value is None:
        return value
    return str(value)


def _default_column_aliases(column_name: str) -> list[str]:
    aliases = {column_name}
    compact = column_name.replace("_", "")
    aliases.add(compact)
    if column_name == "散热器类型":
        aliases.update(["散热方式", "散热类型"])
    if column_name == "触摸屏":
        aliases.update(["触控屏", "支持触摸屏"])
    if column_name in {"型号", "型号名称"}:
        aliases.update(["型号", "款式", "产品型号"])
    if column_name in {"品牌", "品牌名称"}:
        aliases.update(["品牌", "牌子", "厂商"])
    return [item for item in aliases if item]


def _infer_unit(column_name: str) -> str | None:
    if "_" not in column_name:
        return None
    unit = column_name.rsplit("_", 1)[-1]
    if re.fullmatch(r"[A-Za-z%]+(?:/[A-Za-z]+)?", unit):
        return unit
    return None


def _infer_column_role(column_name: str) -> str | None:
    if column_name in {"品牌", "品牌名称"}:
        return "brand"
    if column_name in {"型号", "型号名称", "SKU编码"}:
        return "model"
    return None


def _parse_ddl_comments(ddl_path: str) -> dict:
    """
    从 DDL 文件中提取表名和列名注释。

    解析策略：
    - 以 CREATE TABLE 或 -- table_name 标记识别表
    - 从列定义行提取列名和类型
    - 列名用双引号包裹，如 "品牌" TEXT

    Returns:
        {table_name: {column_name: type_string}}
    """
    ddl_file = Path(ddl_path)
    if not ddl_file.exists():
        return {}

    comments: dict[str, dict[str, str]] = {}
    current_table: str | None = None

    with open(ddl_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            # 匹配 CREATE TABLE 语句
            create_match = re.match(
                r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+"(\w+)"', line, re.IGNORECASE
            )
            if create_match:
                current_table = create_match.group(1)
                comments[current_table] = {}
                continue

            # 匹配注释行标记表名
            comment_match = re.match(r'^--\s+(\w+)\s*$', line)
            if comment_match:
                current_table = comment_match.group(1)
                if current_table not in comments:
                    comments[current_table] = {}
                continue

            # 匹配列定义行: "列名" TYPE,
            if current_table:
                col_match = re.match(r'^\s*"([^"]+)"\s+(\w+)', line)
                if col_match:
                    col_name = col_match.group(1)
                    col_type = col_match.group(2)
                    comments[current_table][col_name] = col_type

    return comments


# ========== 命令行入口 ==========

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from src.config import DB_PATH, RAW_DATA_DIR

    # DDL 文件路径
    ddl_path = RAW_DATA_DIR / "funds_v3_8_tables_ddl.txt"
    if not ddl_path.exists():
        ddl_path = None
        print("(DDL file not found, parsing schema from SQLite only)")

    # 解析 schema
    schema_info = parse_sqlite_schema(str(DB_PATH), str(ddl_path) if ddl_path else None)

    # 展示样例
    print("\n" + "=" * 50)
    print("Sample detail: headphones table")
    print("=" * 50)
    headphones = schema_info["tables"]["headphones"]
    for col in headphones["columns"][:8]:
        print(f"  {col['name']} ({col['type']}) -> {col['sample_values']}")
