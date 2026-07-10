"""
将所有测试样本的 SQL 预测结果写成比赛要求 JSON。

负责人：B
"""

def format_latency(seconds: float) -> str:
    """
    将浮点秒数转成 '1.35s' 形式。
    """
    raise NotImplementedError


def build_submission(team_id: str, predictions: list[dict]) -> dict:
    """
    构建提交 JSON 对象。
    """
    raise NotImplementedError


def save_submission(submission: dict, output_path: str) -> None:
    """
    保存 UTF-8 JSON 文件。
    """
    raise NotImplementedError
