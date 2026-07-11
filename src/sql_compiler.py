"""
Deterministic compiler from QueryIR to SELECT SQL.
"""

from __future__ import annotations

from typing import Any

try:
    from .query_ir import FieldRef, FilterCondition, FilterGroup, OrderItem, QueryIR
except ImportError:
    from query_ir import FieldRef, FilterCondition, FilterGroup, OrderItem, QueryIR


ALLOWED_OPERATORS = {
    "=",
    "!=",
    "<>",
    ">",
    ">=",
    "<",
    "<=",
    "LIKE",
    "IN",
    "BETWEEN",
    "IS",
    "IS NOT",
}


def compile_query_ir(
    query_ir: QueryIR | dict[str, Any],
    join_edges: list[dict] | None = None,
    dialect: str = "mysql",
    qualify_columns: str = "auto",
    trailing_semicolon: bool = False,
) -> str:
    """Compile QueryIR into a deterministic SELECT statement."""
    ir = QueryIR.from_dict(query_ir) if isinstance(query_ir, dict) else query_ir
    if not ir.select_fields and not ir.aggregations:
        raise ValueError("QueryIR must contain select_fields or aggregations")

    tables = _required_tables(ir)
    if not tables:
        raise ValueError("QueryIR must contain at least one required table")

    qualify = _resolve_qualify_columns(tables, ir, qualify_columns)
    select_sql = _compile_select(ir, qualify)
    from_sql = _compile_from(tables, join_edges or [])
    where_sql = _compile_where(ir, qualify)
    group_sql = _compile_group_by(ir.group_by, qualify)
    order_sql = _compile_order_by(ir.order_by, qualify)
    limit_sql = f" LIMIT {int(ir.limit)}" if ir.limit is not None else ""

    distinct_sql = "DISTINCT " if ir.distinct else ""
    sql = f"SELECT {distinct_sql}{select_sql} FROM {from_sql}{where_sql}{group_sql}{order_sql}{limit_sql}"
    if trailing_semicolon:
        sql += ";"
    if not sql.lower().lstrip().startswith("select "):
        raise ValueError("SQLCompiler only generates SELECT SQL")
    return sql


def _required_tables(ir: QueryIR) -> list[str]:
    seen: set[str] = set()
    tables: list[str] = []
    for table in ir.required_tables:
        if table and table not in seen:
            seen.add(table)
            tables.append(table)
    for field in _all_fields(ir):
        if field.table and field.table not in seen:
            seen.add(field.table)
            tables.append(field.table)
    return tables


def _all_fields(ir: QueryIR) -> list[FieldRef]:
    fields = list(ir.select_fields) + list(ir.group_by)
    fields.extend(item.field for item in ir.filters)
    if ir.where:
        fields.extend(_fields_from_filter_group(ir.where))
    fields.extend(item.field for item in ir.order_by)
    for aggregation in ir.aggregations:
        field_data = aggregation.get("field")
        if field_data:
            fields.append(FieldRef.from_dict(field_data))
    return fields


def _fields_from_filter_group(group: FilterGroup) -> list[FieldRef]:
    fields: list[FieldRef] = []
    for item in group.items:
        if isinstance(item, FilterGroup):
            fields.extend(_fields_from_filter_group(item))
        else:
            fields.append(item.field)
    return fields


def _compile_select(ir: QueryIR, qualify: bool) -> str:
    parts: list[str] = []
    for field in ir.select_fields:
        item = _field_sql(field, qualify)
        if field.alias:
            item += f" AS {field.alias}"
        parts.append(item)
    for aggregation in ir.aggregations:
        func = str(aggregation.get("function", "")).upper()
        if func not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:
            raise ValueError(f"unsupported aggregation: {func}")
        field_data = aggregation.get("field")
        arg = "*" if not field_data else _field_sql(FieldRef.from_dict(field_data), qualify)
        item = f"{func}({arg})"
        alias = aggregation.get("alias")
        if alias:
            item += f" AS {alias}"
        parts.append(item)
    return ", ".join(parts)


def _compile_from(tables: list[str], join_edges: list[dict]) -> str:
    if len(tables) == 1:
        return tables[0]

    sql = tables[0]
    joined = {tables[0]}
    remaining = list(tables[1:])
    while remaining:
        table = remaining.pop(0)
        edge = _find_join_edge(join_edges, joined, table)
        if not edge:
            raise ValueError(f"missing join edge for table: {table}")
        sql += f" JOIN {table} ON {_edge_on_clause(edge)}"
        joined.add(table)
    return sql


def _find_join_edge(join_edges: list[dict], joined: set[str], table: str) -> dict | None:
    for edge in join_edges:
        left = edge.get("from") or edge.get("source") or edge.get("left")
        right = edge.get("to") or edge.get("target") or edge.get("right")
        if (left in joined and right == table) or (right in joined and left == table):
            return edge
    return None


def _edge_on_clause(edge: dict) -> str:
    on_clause = edge.get("on") or edge.get("condition")
    if on_clause:
        return str(on_clause)
    left = edge.get("from") or edge.get("source") or edge.get("left")
    right = edge.get("to") or edge.get("target") or edge.get("right")
    column = edge.get("column") or edge.get("field")
    if left and right and column:
        return f"{left}.{column} = {right}.{column}"
    raise ValueError(f"join edge has no ON clause: {edge}")


def _compile_where(ir: QueryIR, qualify: bool) -> str:
    if ir.where:
        body = _compile_filter_group(ir.where, qualify, nested=False)
        return f" WHERE {body}" if body else ""
    return _compile_filters(ir.filters, qualify)


def _compile_filter_group(group: FilterGroup, qualify: bool, nested: bool = True) -> str:
    operator = group.operator.upper()
    if operator not in {"AND", "OR"}:
        raise ValueError(f"unsupported filter group operator: {group.operator}")
    parts = []
    for item in group.items:
        if isinstance(item, FilterGroup):
            part = _compile_filter_group(item, qualify, nested=True)
        else:
            part = _compile_filter_condition(item, qualify)
        if part:
            parts.append(part)
    if not parts:
        return ""
    body = f" {operator} ".join(parts)
    return f"({body})" if nested and len(parts) > 1 else body


def _compile_filters(filters: list[FilterCondition], qualify: bool) -> str:
    if not filters:
        return ""
    parts: list[str] = []
    for idx, item in enumerate(filters):
        condition = _compile_filter_condition(item, qualify)
        if idx:
            condition = f"{item.connector.upper()} {condition}"
        parts.append(condition)
    return " WHERE " + " ".join(parts)


def _compile_filter_condition(item: FilterCondition, qualify: bool) -> str:
    op = item.operator.upper()
    if op not in ALLOWED_OPERATORS:
        raise ValueError(f"unsupported operator: {item.operator}")
    if op in {"IS", "IS NOT"} and item.value is None:
        return f"{_field_sql(item.field, qualify)} {op} NULL"
    return f"{_field_sql(item.field, qualify)} {op} {_value_sql(item.value, op)}"


def _compile_group_by(group_by: list[FieldRef], qualify: bool) -> str:
    if not group_by:
        return ""
    return " GROUP BY " + ", ".join(_field_sql(item, qualify) for item in group_by)


def _compile_order_by(order_by: list[OrderItem], qualify: bool) -> str:
    if not order_by:
        return ""
    parts = []
    for item in order_by:
        direction = item.direction.upper()
        if direction not in {"ASC", "DESC"}:
            raise ValueError(f"unsupported order direction: {item.direction}")
        parts.append(f"{_field_sql(item.field, qualify)} {direction}")
    return " ORDER BY " + ", ".join(parts)


def _field_sql(field: FieldRef, qualify: bool) -> str:
    if not field.table or not field.column:
        raise ValueError("field must include table and column")
    return f"{field.table}.{field.column}" if qualify else field.column


def _value_sql(value: Any, operator: str) -> str:
    if operator in {"IS", "IS NOT"} and value is None:
        return "NULL"
    if operator == "IN":
        if not isinstance(value, (list, tuple, set)):
            value = [value]
        return "(" + ", ".join(_literal_sql(item) for item in value) + ")"
    if operator == "BETWEEN":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("BETWEEN value must contain two items")
        return f"{_literal_sql(value[0])} AND {_literal_sql(value[1])}"
    return _literal_sql(value)


def _literal_sql(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _resolve_qualify_columns(tables: list[str], ir: QueryIR, mode: str) -> bool:
    mode = (mode or "auto").lower()
    if mode == "always":
        return True
    if mode == "never":
        return False
    if mode != "auto":
        raise ValueError(f"unsupported qualify_columns mode: {mode}")
    if len(tables) <= 1:
        return False
    names: dict[str, set[str]] = {}
    for field in _all_fields(ir):
        names.setdefault(field.column, set()).add(field.table)
    return any(len(table_names) > 1 for table_names in names.values())
