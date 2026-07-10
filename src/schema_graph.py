"""
建立表关系图，并为多表查询提供 JOIN 路径。

负责人：A
"""

def build_schema_graph(schema_info: dict, foreign_keys: list[dict] | None = None) -> dict:
    """
    根据 schema 和外键关系构建表关系图。
    如果数据集没有显式外键，则根据相同字段名或 xxx_id 规则推断连接关系。
    """
    raise NotImplementedError


def infer_foreign_keys(schema_info: dict) -> list[dict]:
    """
    当数据集中没有显式外键时，根据字段名推断外键关系。
    例如 product_id、phone_id、brand_id。
    """
    raise NotImplementedError


def find_join_path(graph: dict, start_table: str, end_table: str) -> list[dict]:
    """
    使用 BFS 查找两张表之间的最短 JOIN 路径。
    返回边列表，例如：
    [
        {"from": "product", "to": "sales", "on": "product.id = sales.product_id"}
    ]
    """
    raise NotImplementedError


def find_join_edges_for_tables(graph: dict, tables: list[str]) -> list[dict]:
    """
    为多张表寻找需要的 JOIN 边。
    可以先用第一张表作为起点，分别 BFS 到其他表，再合并边。
    """
    raise NotImplementedError
