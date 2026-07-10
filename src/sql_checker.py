"""
检查 SQL 是否安全、是否只包含 SELECT、是否使用不存在的字段。

负责人：B
"""

from __future__ import annotations

import re


FORBIDDEN_KEYWORDS = {
    "drop",
    "delete",
    "update",
    "insert",
    "alter",
    "create",
    "truncate",
    "replace",
    "attach",
    "detach",
    "pragma",
}

SQL_KEYWORDS = {
    "select",
    "from",
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "on",
    "and",
    "or",
    "group",
    "by",
    "order",
    "limit",
    "having",
    "as",
    "with",
}


def extract_sql(text: str) -> str:
    """
    从模型输出中提取 SQL（去掉 markdown 代码块等）。
    """
    if text is None:
        return ""
    value = str(text).strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", value, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    match = re.search(r"\b(with|select)\b", value, flags=re.IGNORECASE)
    if match:
        value = value[match.start() :]
    return value.strip()


def is_select_only(sql: str) -> bool:
    """
    检查是否只包含 SELECT 查询。
    禁止 DROP、DELETE、UPDATE、INSERT 等操作。
    """
    cleaned = _strip_comments(normalize_sql(sql)).strip()
    if not cleaned:
        return False
    body = cleaned[:-1].strip() if cleaned.endswith(";") else cleaned
    if ";" in body:
        return False
    if not re.match(r"^(select|with)\b", body, flags=re.IGNORECASE):
        return False
    lowered = body.lower()
    return not any(re.search(rf"\b{keyword}\b", lowered) for keyword in FORBIDDEN_KEYWORDS)


def validate_sql_schema(sql: str, schema_info: dict) -> list[str]:
    """
    检查 SQL 中的表名和字段名是否存在。
    返回错误列表。
    """
    errors: list[str] = []
    tables_info = (schema_info or {}).get("tables", {})
    if not isinstance(tables_info, dict) or not tables_info:
        return errors

    known_tables = {str(name).lower(): str(name) for name in tables_info}
    table_refs, aliases = _extract_table_refs(sql)
    for table in table_refs:
        if table.lower() not in known_tables:
            errors.append(f"unknown table: {table}")

    qualified_columns = re.findall(
        r"([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)\.([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)",
        sql,
    )
    for qualifier, column in qualified_columns:
        table_name = aliases.get(qualifier.lower(), qualifier)
        canonical = known_tables.get(table_name.lower())
        if not canonical:
            errors.append(f"unknown table or alias: {qualifier}")
            continue
        columns = _columns_for_table(tables_info[canonical])
        if column.lower() not in columns:
            errors.append(f"unknown column: {qualifier}.{column}")
    return errors


def normalize_sql(sql: str) -> str:
    """
    格式化 SQL，去除多余换行和 markdown 代码块。
    """
    value = extract_sql(sql)
    value = _strip_comments(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*;\s*$", ";", value)
    return value


def _strip_comments(sql: str) -> str:
    value = re.sub(r"--.*?(?=\n|$)", " ", sql)
    return re.sub(r"/\*.*?\*/", " ", value, flags=re.DOTALL)


def _extract_table_refs(sql: str) -> tuple[list[str], dict[str, str]]:
    refs: list[str] = []
    aliases: dict[str, str] = {}
    pattern = re.compile(
        r"\b(?:from|join)\s+([`\"\[]?[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*[`\"\]]?)"
        r"(?:\s+(?:as\s+)?([`\"\[]?[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*[`\"\]]?))?",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        table = _clean_identifier(match.group(1))
        alias = _clean_identifier(match.group(2) or "")
        refs.append(table)
        aliases[table.lower()] = table
        if alias and alias.lower() not in SQL_KEYWORDS:
            aliases[alias.lower()] = table
    return refs, aliases


def _clean_identifier(identifier: str) -> str:
    return identifier.strip().strip("`\"[]")


def _columns_for_table(table_info: object) -> set[str]:
    if not isinstance(table_info, dict):
        return set()
    columns = table_info.get("columns", [])
    names = set()
    for column in columns:
        if isinstance(column, dict):
            name = column.get("name") or column.get("field") or column.get("column")
        else:
            name = column
        if name:
            names.add(str(name).lower())
    return names
