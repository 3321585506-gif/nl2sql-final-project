"""
根据用户 query 检索最相关的表、字段和示例 SQL。

负责人：A
"""

def retrieve_schema_context(
    question: str,
    schema_info: dict,
    alias_map: dict,
    inverted_index: dict,
    top_k_fields: int = 20
) -> dict:
    """
    综合哈希表和倒排索引，返回和问题最相关的 schema 上下文。

    Returns:
        {
            "tables": ["phone", "product"],
            "fields": [
                {"table": "phone", "field": "model_name", "score": 3},
                {"table": "phone", "field": "battery_capacity", "score": 2}
            ],
            "matched_keywords": ["手机", "电池容量"]
        }
    """
    raise NotImplementedError


def rank_fields(question: str, candidates: list[dict]) -> list[dict]:
    """
    对候选字段打分排序。
    """
    raise NotImplementedError


def retrieve_by_keywords(question: str, inverted_index: dict, top_k: int = 10) -> list[dict]:
    """
    根据用户问题中的关键词，从倒排索引中检索相关字段。
    """
    raise NotImplementedError


# ========== 查询缓存 ==========

def normalize_question(question: str) -> str:
    """
    标准化 query，用于缓存 key。
    """
    raise NotImplementedError


def get_cached_sql(question: str, cache: dict) -> str | None:
    """
    从缓存中读取 SQL。
    """
    raise NotImplementedError


def update_sql_cache(question: str, sql: str, cache: dict) -> None:
    """
    将新生成的 SQL 写入缓存。
    """
    raise NotImplementedError


# ========== 向量索引（增强模块，最小系统可暂不实现） ==========

def build_vector_index(schema_docs: list[dict]) -> object:
    """
    构建字段描述或示例 SQL 的向量索引。
    最小版本可以先返回 embedding 矩阵。
    """
    raise NotImplementedError


def retrieve_by_vector(question: str, vector_index: object, top_k: int = 5) -> list[dict]:
    """
    使用语义相似度检索相关字段或历史样例。
    """
    raise NotImplementedError
