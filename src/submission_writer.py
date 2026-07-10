"""
将所有测试样本的 SQL 预测结果写成比赛要求 JSON。

负责人：B
"""

from __future__ import annotations

import json
from pathlib import Path


def format_latency(seconds: float) -> str:
    """
    将浮点秒数转成 '1.35s' 形式。
    """
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        value = 0.0
    return f"{max(value, 0.0):.2f}s"


def build_submission(team_id: str, predictions: list[dict]) -> dict:
    """
    构建提交 JSON 对象。
    """
    results = []
    for index, prediction in enumerate(predictions):
        item_id = prediction.get("id", index)
        query = prediction.get("query") or prediction.get("question") or ""
        predicted_sql = prediction.get("predicted_sql") or prediction.get("sql") or ""
        latency = prediction.get("lantancy", prediction.get("latency", 0.0))
        results.append(
            {
                "id": str(item_id),
                "query": str(query),
                "predicted_sql": str(predicted_sql),
                "lantancy": latency if isinstance(latency, str) else format_latency(latency),
            }
        )
    return {"team_id": str(team_id), "results": results}


def save_submission(submission: dict, output_path: str) -> None:
    """
    保存 UTF-8 JSON 文件。
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(submission, file, ensure_ascii=False, indent=2)
