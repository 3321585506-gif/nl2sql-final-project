"""
Structured intermediate representation for NL2SQL queries.

The parser and LLM fallback should build QueryIR; SQLCompiler is responsible
for turning it into a deterministic SQL string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldRef:
    table: str
    column: str
    alias: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {"table": self.table, "column": self.column}
        if self.alias is not None:
            data["alias"] = self.alias
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | "FieldRef") -> "FieldRef":
        if isinstance(data, FieldRef):
            return data
        return cls(
            table=str(data.get("table", "")),
            column=str(data.get("column") or data.get("field") or data.get("name") or ""),
            alias=data.get("alias"),
        )


@dataclass
class FilterCondition:
    field: FieldRef
    operator: str
    value: Any
    connector: str = "AND"

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field.to_dict(),
            "operator": self.operator,
            "value": self.value,
            "connector": self.connector,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | "FilterCondition") -> "FilterCondition":
        if isinstance(data, FilterCondition):
            return data
        field_data = data.get("field") or {
            "table": data.get("table", ""),
            "column": data.get("column") or data.get("field_name") or data.get("field") or "",
        }
        return cls(
            field=FieldRef.from_dict(field_data),
            operator=str(data.get("operator", "=")),
            value=data.get("value"),
            connector=str(data.get("connector", "AND")).upper(),
        )


@dataclass
class FilterGroup:
    operator: str = "AND"
    items: list[FilterCondition | "FilterGroup"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator": self.operator.upper(),
            "items": [
                item.to_dict() | {"kind": "group" if isinstance(item, FilterGroup) else "condition"}
                for item in self.items
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | "FilterGroup" | None) -> "FilterGroup | None":
        if data is None:
            return None
        if isinstance(data, FilterGroup):
            return data
        items: list[FilterCondition | FilterGroup] = []
        for item in data.get("items", []):
            kind = item.get("kind")
            if kind == "group" or "items" in item:
                group = cls.from_dict(item)
                if group is not None:
                    items.append(group)
            else:
                items.append(FilterCondition.from_dict(item))
        return cls(operator=str(data.get("operator", "AND")).upper(), items=items)


@dataclass
class OrderItem:
    field: FieldRef
    direction: str = "ASC"

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field.to_dict(), "direction": self.direction}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | "OrderItem") -> "OrderItem":
        if isinstance(data, OrderItem):
            return data
        field_data = data.get("field") or {
            "table": data.get("table", ""),
            "column": data.get("column") or data.get("field_name") or data.get("field") or "",
        }
        return cls(
            field=FieldRef.from_dict(field_data),
            direction=str(data.get("direction", "ASC")).upper(),
        )


@dataclass
class QueryIR:
    select_fields: list[FieldRef] = field(default_factory=list)
    aggregations: list[dict[str, Any]] = field(default_factory=list)
    filters: list[FilterCondition] = field(default_factory=list)
    where: FilterGroup | None = None
    group_by: list[FieldRef] = field(default_factory=list)
    order_by: list[OrderItem] = field(default_factory=list)
    required_tables: list[str] = field(default_factory=list)
    limit: int | None = None
    distinct: bool = False
    confidence: float = 0.0
    source: str = "rule"

    def to_dict(self) -> dict[str, Any]:
        return {
            "select_fields": [item.to_dict() for item in self.select_fields],
            "aggregations": list(self.aggregations),
            "filters": [item.to_dict() for item in self.filters],
            "where": self.where.to_dict() if self.where else None,
            "group_by": [item.to_dict() for item in self.group_by],
            "order_by": [item.to_dict() for item in self.order_by],
            "required_tables": list(self.required_tables),
            "limit": self.limit,
            "distinct": self.distinct,
            "confidence": self.confidence,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | "QueryIR") -> "QueryIR":
        if isinstance(data, QueryIR):
            return data
        filters = [FilterCondition.from_dict(item) for item in data.get("filters", [])]
        where = FilterGroup.from_dict(data.get("where"))
        if where is None and filters:
            where = FilterGroup(operator="AND", items=list(filters))
        return cls(
            select_fields=[FieldRef.from_dict(item) for item in data.get("select_fields", [])],
            aggregations=list(data.get("aggregations", [])),
            filters=filters,
            where=where,
            group_by=[FieldRef.from_dict(item) for item in data.get("group_by", [])],
            order_by=[OrderItem.from_dict(item) for item in data.get("order_by", [])],
            required_tables=[str(item) for item in data.get("required_tables", [])],
            limit=data.get("limit"),
            distinct=bool(data.get("distinct", False)),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            source=str(data.get("source", "rule")),
        )
