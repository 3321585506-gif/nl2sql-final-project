"""
建立表关系图，并为多表查询提供 JOIN 路径。

负责人：A

图结构：
- 顶点 = 数据表
- 边 = 外键关系（或根据字段名推断的 JOIN 条件）

核心算法：
- BFS 查找两张表之间的最短 JOIN 路径
- 复杂度 O(V + E)，V ≈ 8，E ≈ 5

实际表关系（8_tables 数据集）：
- 独立表：air_conditioner, desktop_computer, digital_camera, electric_vehicle, headphones
- 关联表组：computer_join_main ←→ computer_join_config ←→ computer_join_price
  共享字段: 笔记本ID, 品牌ID, 系列ID, 型号ID, SKU_ID, 配置ID
"""

from collections import deque
from pathlib import Path


# ========== 外键推断 ==========

def infer_foreign_keys(schema_info: dict) -> list[dict]:
    """
    当数据集中没有显式外键时，根据字段名推断外键关系。

    推断规则（保守策略，避免将普通同名列误判为外键）：
    1. 只考虑以 "ID" 结尾或包含 "_id" 的列名 → 强外键信号
    2. 该列必须在至少 2 张表中出现
    3. 排除在所有表中都出现的 ID 列（太泛化，如主键 id）

    注意：像"品牌""型号"这样的列名虽然在多张表中存在，但它们
    是业务属性值而非外键引用，不会被纳入外键推断。

    Args:
        schema_info: 数据库结构

    Returns:
        [{"from": "table_a", "to": "table_b", "columns": ["col1"], "on": "a.col1 = b.col1"}]
    """
    total_tables = len(schema_info["tables"])

    # 收集 {column_name: [table_names]}，只收集 ID 类型列
    col_to_tables: dict[str, list[str]] = {}
    for table_name, table_info in schema_info["tables"].items():
        for col in table_info["columns"]:
            col_name = col["name"]
            # 只关注 ID 类型的列
            if col_name.endswith("ID") or "_id" in col_name.lower():
                if col_name not in col_to_tables:
                    col_to_tables[col_name] = []
                col_to_tables[col_name].append(table_name)

    foreign_keys: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for col_name, tables in col_to_tables.items():
        # 只在 2 张或少数表中出现（不在所有表中）
        if len(tables) < 2:
            continue
        if len(tables) == total_tables:
            continue  # 在所有表中都出现，太泛化

        for i in range(len(tables)):
            for j in range(i + 1, len(tables)):
                t1, t2 = tables[i], tables[j]
                pair = (t1, t2) if t1 < t2 else (t2, t1)

                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    foreign_keys.append({
                        "from": t1,
                        "to": t2,
                        "columns": [col_name],
                        "on": f'"{t1}"."{col_name}" = "{t2}"."{col_name}"',
                        "confidence": "high",
                    })

    print(f"Inferred {len(foreign_keys)} foreign key relationships (ID columns only)")
    for fk in foreign_keys:
        print(f"  {fk['from']} ←→ {fk['to']}  on [{', '.join(fk['columns'])}]")

    return foreign_keys


# ========== 图构建 ==========

def build_schema_graph(
    schema_info: dict,
    foreign_keys: list[dict] | None = None
) -> dict[str, list[dict]]:
    """
    构建表关系图（邻接表）。

    Args:
        schema_info: 数据库结构
        foreign_keys: 外键列表，如果为 None 则自动推断

    Returns:
        graph = {
            "table_a": [
                {"from": "table_a", "to": "table_b", "on": "a.col = b.col"}
            ],
            ...
        }
    """
    if foreign_keys is None:
        foreign_keys = infer_foreign_keys(schema_info)

    graph: dict[str, list[dict]] = {}

    # 初始化所有表节点（确保独立表也在图中）
    for table_name in schema_info["tables"]:
        graph[table_name] = []

    # 添加边（无向图，每条外键添加两个方向的边）
    for fk in foreign_keys:
        t_from, t_to = fk["from"], fk["to"]

        # t_from → t_to
        graph[t_from].append({
            "from": t_from,
            "to": t_to,
            "on": fk["on"],
            "columns": fk.get("columns", []),
            "confidence": fk.get("confidence", "medium"),
        })

        # t_to → t_from（反向边）
        # ON 条件翻转
        on_reversed = fk["on"]
        if f'"{t_from}"' in on_reversed and f'"{t_to}"' in on_reversed:
            on_reversed = on_reversed.replace(f'"{t_from}"', '"__SRC__"') \
                                     .replace(f'"{t_to}"', f'"{t_from}"') \
                                     .replace('"__SRC__"', f'"{t_to}"')

        graph[t_to].append({
            "from": t_to,
            "to": t_from,
            "on": on_reversed,
            "columns": fk.get("columns", []),
            "confidence": fk.get("confidence", "medium"),
        })

    connected = sum(1 for v in graph.values() if len(v) > 0)
    isolated = len(graph) - connected
    print(f"Graph built: {len(graph)} nodes, {connected} connected, {isolated} isolated")

    return graph


# ========== BFS JOIN 路径搜索 ==========

def find_join_path(graph: dict, start_table: str, end_table: str) -> list[dict]:
    """
    使用 BFS 查找两张表之间的最短 JOIN 路径。

    Args:
        graph: 表关系图（邻接表）
        start_table: 起始表
        end_table: 目标表

    Returns:
        边列表（按遍历顺序），如果找不到路径则返回空列表
        示例: [
            {"from": "product", "to": "sales", "on": "product.id = sales.product_id"}
        ]
    """
    if start_table == end_table:
        return []  # 同一张表，不需要 JOIN

    if start_table not in graph or end_table not in graph:
        return []

    # BFS
    queue = deque([(start_table, [])])  # (当前节点, 路径边列表)
    visited = {start_table}

    while queue:
        current, path = queue.popleft()

        for edge in graph.get(current, []):
            neighbor = edge["to"]

            if neighbor == end_table:
                # 找到目标，返回完整路径
                return path + [edge]

            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [edge]))

    # 找不到路径（独立表间无 JOIN 关系，属于正常情况）
    return []


def find_join_edges_for_tables(graph: dict, tables: list[str]) -> list[dict]:
    """
    为多张表寻找需要的 JOIN 边（最小生成树风格）。

    策略：
    - 以第一张表为起点
    - BFS 到其他各表 → 收集最短路径上的边
    - 去重合并

    Args:
        graph: 表关系图
        tables: 需要的表列表

    Returns:
        去重后的 JOIN 边列表（每条边只出现一次）
    """
    if len(tables) <= 1:
        return []

    all_edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()

    start = tables[0]

    for target in tables[1:]:
        path = find_join_path(graph, start, target)
        for edge in path:
            # 用排序后的表名对作为边的唯一标识（无向图）
            pair = tuple(sorted([edge["from"], edge["to"]]))
            if pair not in seen_edges:
                seen_edges.add(pair)
                all_edges.append(edge)

    return all_edges


# ========== 格式化输出 ==========

def join_edges_to_sql(join_edges: list[dict]) -> str:
    """
    将 JOIN 边列表转成 SQL JOIN 子句。

    Args:
        join_edges: JOIN 边列表

    Returns:
        SQL JOIN 字符串，如:
        "JOIN sales ON product.id = sales.product_id"
    """
    clauses: list[str] = []
    for edge in join_edges:
        to_table = edge["to"]
        on = edge["on"]
        clauses.append(f'JOIN "{to_table}" ON {on}')
    return "\n".join(clauses)


# ========== 命令行入口 ==========

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from src.config import DB_PATH
    from src.schema_parser import parse_sqlite_schema

    print("=" * 50)
    print("Step 1: Parse schema + Infer foreign keys")
    print("=" * 50)
    schema_info = parse_sqlite_schema(str(DB_PATH))

    print("\n" + "=" * 50)
    print("Step 2: Build graph")
    print("=" * 50)
    graph = build_schema_graph(schema_info)

    print("\n" + "=" * 50)
    print("Step 3: Test JOIN path search")
    print("=" * 50)

    # 测试用例
    test_cases = [
        # 关联表间 JOIN
        ("computer_join_main", "computer_join_price"),
        ("computer_join_main", "computer_join_config"),
        ("computer_join_config", "computer_join_price"),
        # 同表（无需 JOIN）
        ("computer_join_main", "computer_join_main"),
        # 无关联表（独立表间无法 JOIN）
        ("headphones", "air_conditioner"),
    ]

    for start, end in test_cases:
        print(f"\n  {start} → {end}:")
        path = find_join_path(graph, start, end)
        if path:
            for edge in path:
                print(f"    {edge['from']} → {edge['to']}")
                print(f"    ON: {edge['on']}")
        else:
            if start == end:
                print("    (same table, no JOIN needed)")
            else:
                print("    (no path — independent tables)")

    print("\n" + "=" * 50)
    print("Step 4: Test multi-table JOIN edges")
    print("=" * 50)

    # 多表 JOIN 场景
    tables_needed = ["computer_join_main", "computer_join_price", "computer_join_config"]
    edges = find_join_edges_for_tables(graph, tables_needed)
    print(f"\n  Tables: {tables_needed}")
    if edges:
        print(f"  JOIN edges ({len(edges)}):")
        for e in edges:
            print(f"    {e['from']} → {e['to']}  ON {e['on']}")
        print(f"\n  SQL JOIN clause:")
        print(f"  {join_edges_to_sql(edges)}")
    else:
        print("  No JOINs needed")
