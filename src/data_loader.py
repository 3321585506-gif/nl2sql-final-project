"""
读取比赛提供的 CSV / Excel / JSON 数据，将数据统一导入 SQLite 或 DuckDB。

负责人：A
"""

def load_tables_from_directory(data_dir: str) -> dict[str, "pd.DataFrame"]:
    """
    读取目录下所有 csv/xlsx/json 文件，返回 {table_name: DataFrame}。
    """
    raise NotImplementedError


def save_tables_to_sqlite(tables: dict, db_path: str) -> None:
    """
    将多个 DataFrame 保存到 SQLite 数据库中。
    """
    raise NotImplementedError


def load_test_queries(test_file: str) -> list[dict]:
    """
    读取测试集 JSON，返回 query 列表。
    每个元素至少包含 id 和 query。
    """
    raise NotImplementedError
