"""
验证集评估脚本（v2 优化版）：含 Few-shot 示例选择和完整评估。

用法:
    python run_eval.py [--full] [--limit N]

    --full  跑全部 200 条（默认跑 20 条快速验证）
    --limit N  指定跑 N 条

前置条件:
    - OPENAI_API_KEY + OPENAI_BASE_URL 环境变量已设置
    - 数据库已通过 data_loader 构建完成
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve()))

from src.config import (
    PROJECT_ROOT, DB_PATH, TEAM_ID,
    LLM_PROVIDER, LLM_MODEL, MAX_SCHEMA_FIELDS, MAX_EXAMPLES,
)
from src.schema_parser import parse_sqlite_schema
from src.index_builder import load_index
from src.schema_graph import build_schema_graph
from src.llm_client import LLMClient
from src.sql_generator import generate_sql_for_question
from src.submission_writer import format_latency, build_submission, save_submission
from src.data_loader import load_test_queries
from src.retriever import select_fewshot_examples
from src.evaluation import (
    evaluate_predictions, print_evaluation_report,
    exact_match_accuracy, average_latency_score, final_score,
    _normalize_sql_for_compare,
)

VALIDATION_FILE = PROJECT_ROOT / "初赛数据集" / "初赛_验证集 .jsonl"
EVAL_OUTPUT = PROJECT_ROOT / "outputs" / "predictions_val.json"


def main(full: bool = False, limit: int | None = None):
    n_samples = limit or (200 if full else 20)
    print("=" * 60)
    print(f"  NL2SQL Validation Evaluation (v2 + Few-shot)")
    print(f"  LLM: {LLM_PROVIDER} / {LLM_MODEL}")
    print(f"  Samples: {n_samples}")
    print(f"  Max Schema Fields: {MAX_SCHEMA_FIELDS}")
    print("=" * 60)

    # ===== 加载资源 =====
    print("\n[Loading] schema, indexes, graph...")
    schema_info = parse_sqlite_schema(str(DB_PATH))
    processed = PROJECT_ROOT / "data" / "processed"
    alias_map = load_index(str(processed / "alias_map.json"))
    inverted_index = load_index(str(processed / "inverted_index.json"))
    graph = build_schema_graph(schema_info)

    llm_client = LLMClient(
        provider=os.getenv("LLM_PROVIDER", LLM_PROVIDER),
        model=os.getenv("LLM_MODEL", LLM_MODEL),
    )

    # 加载验证集（作为 ground truth + few-shot 候选池）
    all_records = load_test_queries(str(VALIDATION_FILE))
    records = all_records[:n_samples]

    print(f"  Loaded {len(records)} validation queries")

    # ===== 逐条生成 =====
    print(f"\n[Running] Generating SQL for {len(records)} queries...\n")

    predictions = []
    correct = 0

    for i, item in enumerate(records):
        question = item.get("query", "")
        gold_sql = item.get("sql", "")

        # 构建 indexes
        indexes = {
            "alias_map": alias_map,
            "inverted_index": inverted_index,
            "top_k_fields": MAX_SCHEMA_FIELDS,
            "examples": [],
        }

        result = generate_sql_for_question(
            question=question,
            schema_info=schema_info,
            indexes=indexes,
            graph=graph,
            llm_client=llm_client,
        )

        pred_sql = result["predicted_sql"]
        latency = result["latency"]

        # 实时对比
        is_match = _normalize_sql_for_compare(pred_sql) == _normalize_sql_for_compare(gold_sql)
        if is_match:
            correct += 1

        predictions.append({
            "id": item.get("id", f"Q{i+1:04d}"),
            "query": question,
            "predicted_sql": pred_sql,
            "lantancy": format_latency(latency),
            "error": result.get("error"),
        })

        status = "MATCH" if is_match else "DIFF"
        bar = "=" if is_match else "-"
        print(f" [{i+1:3d}/{len(records)}] {status} | {latency:.2f}s | {question[:50]}...")
        if not is_match:
            print(f"   Pred: {pred_sql[:100]}")
            print(f"   Gold: {gold_sql[:100]}")

    # ===== 保存 & 评估 =====
    submission = build_submission(TEAM_ID, predictions)
    save_submission(submission, str(EVAL_OUTPUT))

    result = evaluate_predictions(
        predictions_file=str(EVAL_OUTPUT),
        validation_file=str(VALIDATION_FILE),
        db_path=str(DB_PATH),
    )
    print_evaluation_report(result)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Run all 200 queries")
    parser.add_argument("--limit", type=int, default=None, help="Run N queries")
    args = parser.parse_args()
    main(full=args.full, limit=args.limit)
