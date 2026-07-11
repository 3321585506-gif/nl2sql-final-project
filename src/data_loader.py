"""
读取比赛提供的 CSV / Excel / JSON 数据，将数据统一导入 SQLite 或 DuckDB。

负责人：A

数据来源：
- 8 张表的 xlsx 文件（air_conditioner, desktop_computer, digital_camera,
  electric_vehicle, headphones, computer_join_main, computer_join_config,
  computer_join_price）
- JSONL 格式的测试集 / 验证集文件
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd


# ========== 数据读取 ==========

def load_tables_from_directory(data_dir: str) -> dict[str, "pd.DataFrame"]:
    """
    读取目录下所有 xlsx 文件，返回 {table_name: DataFrame}。

    规则：
    - 只处理 .xlsx 文件，忽略 .txt / .zip / .json 等
    - 文件名（不含扩展名）作为表名
    - 如果 Excel 有多个 sheet，表名格式为 "文件名_sheet名"
    - 列名自动去除首尾空格

    Args:
        data_dir: 数据目录路径

    Returns:
        {table_name: DataFrame}
    """
    data_path = Path(data_dir)
    tables: dict[str, pd.DataFrame] = {}

    for file_path in sorted(data_path.glob("*.xlsx")):
        xlsx = pd.ExcelFile(file_path)
        base_name = file_path.stem  # 不含扩展名的文件名

        for sheet_name in xlsx.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            # 清理列名：去首尾空格
            df.columns = [str(col).strip() for col in df.columns]

            # 单 sheet → 表名 = 文件名；多 sheet → 表名 = 文件名_sheet名
            if len(xlsx.sheet_names) == 1:
                table_name = base_name
            else:
                table_name = f"{base_name}_{sheet_name}"

            tables[table_name] = df
            print(f"  [OK] {file_path.name} -> table '{table_name}' ({df.shape[0]} rows x {df.shape[1]} cols)")

    print(f"\nTotal: {len(tables)} tables, {sum(len(df) for df in tables.values())} rows")
    return tables


# ========== 数据入库 ==========

def save_tables_to_sqlite(tables: dict, db_path: str) -> None:
    """
    将多个 DataFrame 保存到 SQLite 数据库中。

    - 使用 if_exists='replace'，每次运行会覆盖同名表
    - 自动创建数据库目录（如不存在）

    Args:
        tables: {table_name: DataFrame}
        db_path: SQLite 数据库文件路径
    """
    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path_obj))

    for table_name, df in tables.items():
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"  [OK] -> SQLite: '{table_name}' ({df.shape[0]} rows x {df.shape[1]} cols)")

    conn.close()
    print(f"\nDatabase saved to: {db_path_obj.resolve()}")


# ========== 测试集读取 ==========

def load_test_queries(test_file: str) -> list[dict]:
    """
    读取 JSONL 格式的测试集 / 验证集文件。

    每行一个 JSON 对象，支持两种格式：
    1. 测试集（无 ground truth）：
       {"query": "..."}
       → 自动生成 id = "Q001", "Q002", ...

    2. 验证集（含 ground truth）：
       {"query": "...", "sql": "SELECT ...", "table": "...", "type": ..., "used": ...}
       → 保留原始字段，同时确保有 id 字段

    Args:
        test_file: JSONL 文件路径

    Returns:
        list[dict]，每个元素至少包含 id 和 query
    """
    test_path = Path(test_file)
    queries: list[dict] = []

    with open(test_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:  # 跳过空行
                continue

            record = json.loads(line)

            # 确保有 id 字段
            if "id" not in record:
                record["id"] = f"Q{idx + 1:04d}"

            queries.append(record)

    # 统计信息
    has_sql = sum(1 for q in queries if "sql" in q and q["sql"])
    print(f"Loaded test file: {test_path.name}")
    print(f"  {len(queries)} queries total")
    print(f"  {has_sql} with ground truth SQL")

    return queries


# ========== 便捷函数 ==========

def build_database(data_dir: str, db_path: str) -> dict:
    """
    一站式：读取目录下所有 xlsx 并导入 SQLite。

    Args:
        data_dir: 原始数据目录
        db_path: 目标 SQLite 数据库路径

    Returns:
        {table_name: DataFrame}
    """
    print("=" * 50)
    print("Step 1: Read xlsx files")
    print("=" * 50)
    tables = load_tables_from_directory(data_dir)

    print("\n" + "=" * 50)
    print("Step 2: Write to SQLite")
    print("=" * 50)
    save_tables_to_sqlite(tables, db_path)

    return tables


# ========== 命令行入口 ==========

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from src.config import RAW_DATA_DIR, DB_PATH

    # 构建数据库
    tables = build_database(str(RAW_DATA_DIR), str(DB_PATH))

    # 打印摘要
    print("\n" + "=" * 50)
    print("Data Summary")
    print("=" * 50)
    for name, df in tables.items():
        print(f"\n[{name}]")
        print(f"  Columns ({len(df.columns)}): {list(df.columns[:5])}...")
        print(f"  Dtypes: {dict(df.dtypes.value_counts().items())}")
