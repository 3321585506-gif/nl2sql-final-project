"""
对自然语言问题进行预处理，抽取品牌、型号、数值条件、排序条件、聚合意图等。

负责人：A + B
"""

def normalize_text(text: str) -> str:
    """
    统一中英文符号、去除多余空格、大小写归一化。
    """
    raise NotImplementedError


def extract_numbers_and_units(question: str) -> list[dict]:
    """
    抽取数值和单位，例如 5000mAh、95%、5000到10000元。
    """
    raise NotImplementedError


def detect_query_intent(question: str) -> dict:
    """
    检测查询意图。

    Returns:
        {
            "need_aggregation": True,
            "aggregation_type": "AVG",
            "need_group_by": True,
            "need_order_by": True,
            "filters": [...]
        }
    """
    raise NotImplementedError
