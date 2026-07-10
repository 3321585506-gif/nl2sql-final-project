"""
解析数据库表结构，生成给检索模块和 PromptBuilder 使用的 schema_info。

负责人：A
"""

def parse_sqlite_schema(db_path: str) -> dict:
    """
    解析 SQLite 数据库结构。

    Returns:
        {
            "tables": {
                "phone": {
                    "columns": [
                        {
                            "name": "model_name",
                            "type": "TEXT",
                            "description": "",
                            "sample_values": ["小米14", "荣耀100 Pro"]
                        }
                    ]
                }
            }
        }
    """
    raise NotImplementedError


def collect_sample_values(db_path: str, table: str, column: str, limit: int = 5) -> list:
    """
    从数据库中抽取字段样例值，帮助大模型理解字段含义。
    """
    raise NotImplementedError
