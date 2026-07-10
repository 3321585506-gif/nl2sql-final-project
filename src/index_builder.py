"""
构建字段别名哈希表和倒排索引。

负责人：A
"""

def build_alias_map(schema_info: dict, extra_aliases: dict | None = None) -> dict:
    """
    根据数据库 schema 和人工补充别名，构建字段别名哈希表。

    Args:
        schema_info: schema_parser.py 解析出的数据库结构。
        extra_aliases: 人工补充的中文别名词典。

    Returns:
        alias_map: dict[str, list[dict]]
    """
    raise NotImplementedError


def build_inverted_index(schema_info: dict, alias_map: dict) -> dict:
    """
    构建关键词到表字段列表的倒排索引。
    """
    raise NotImplementedError


def save_index(index: dict, path: str) -> None:
    """
    保存索引到 JSON 文件。
    """
    raise NotImplementedError


def load_index(path: str) -> dict:
    """
    从 JSON 文件读取索引。
    """
    raise NotImplementedError
