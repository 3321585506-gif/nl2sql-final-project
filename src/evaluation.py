"""
在本地测试集上评估 SQL 准确率、执行结果一致率和延迟得分。

负责人：A
"""

def exact_match_accuracy(pred_sqls: list[str], gold_sqls: list[str]) -> float:
    """
    计算 SQL 字符串完全匹配准确率。
    """
    raise NotImplementedError


def execution_match_accuracy(pred_results: list, gold_results: list) -> float:
    """
    计算执行结果一致率。
    """
    raise NotImplementedError


def latency_score(t: float) -> float:
    """
    根据比赛规则计算单条样本延迟得分。
    """
    raise NotImplementedError


def average_latency_score(latencies: list[float]) -> float:
    """
    计算平均延迟得分。
    """
    raise NotImplementedError


def final_score(em: float, ls: float) -> float:
    """
    初赛总分：Score = EM * 0.8 + LS * 0.2
    """
    raise NotImplementedError
