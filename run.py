"""
项目统一入口。支持三种模式：

用法:
    python run.py                   默认：在测试集上生成提交文件
    python run.py --eval            验证集评估（含 EM/EX/LS 报告）
    python run.py --query           交互式查询模式
    python run.py -q "查询内容"      单次查询模式

前置条件:
    - 数据库已构建: python src/data_loader.py
    - LLM API Key 已设置（或用 mock 测试）
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve()))

from src.config import (
    PROJECT_ROOT, DB_PATH, OUTPUT_PATH, TEAM_ID,
    LLM_PROVIDER, LLM_MODEL, MAX_SCHEMA_FIELDS,
)
from src.main import run_pipeline
from src.evaluation import evaluate_predictions, print_evaluation_report
from src.schema_parser import parse_sqlite_schema
from src.index_builder import load_index
from src.schema_graph import build_schema_graph
from src.llm_client import LLMClient
from src.sql_generator import generate_sql_for_question
from src.sql_executor import execute_sql
from src.answer_polisher import polish_answer
from src.data_loader import load_test_queries

# 文件路径
TEST_FILE = PROJECT_ROOT / "初赛数据集" / "初赛_测试集.jsonl"
VALIDATION_FILE = PROJECT_ROOT / "初赛数据集" / "初赛_验证集 .jsonl"
EVAL_OUTPUT = PROJECT_ROOT / "outputs" / "predictions_val.json"


# ========== 模式1: 测试集生成 ==========

def mode_submit():
    """在测试集上生成提交 JSON。"""
    print("=" * 50)
    print("  Mode: Submit (test set)")
    print(f"  LLM: {LLM_PROVIDER} / {LLM_MODEL}")
    print("=" * 50)
    run_pipeline(str(TEST_FILE), str(OUTPUT_PATH))
    print(f"\nDone -> {OUTPUT_PATH}")


# ========== 模式2: 验证集评估 ==========

def mode_eval():
    """在验证集上生成 SQL 并评估。"""
    print("=" * 50)
    print("  Mode: Evaluation (validation set)")
    print(f"  LLM: {LLM_PROVIDER} / {LLM_MODEL}")
    print("=" * 50)

    run_pipeline(str(VALIDATION_FILE), str(EVAL_OUTPUT))

    print("\n[Evaluate] Comparing against ground truth...")
    result = evaluate_predictions(
        predictions_file=str(EVAL_OUTPUT),
        validation_file=str(VALIDATION_FILE),
        db_path=str(DB_PATH),
    )
    print_evaluation_report(result)


# ========== 模式3&4: 交互 / 单次查询 ==========

def _load_context():
    """加载一次性的上下文（schema、索引、图、LLM 客户端）。"""
    schema_info = parse_sqlite_schema(str(DB_PATH))
    processed = PROJECT_ROOT / "data" / "processed"
    alias_map = load_index(str(processed / "alias_map.json"))
    inverted = load_index(str(processed / "inverted_index.json"))
    graph = build_schema_graph(schema_info)
    client = LLMClient(
        provider=os.getenv("LLM_PROVIDER", LLM_PROVIDER),
        model=os.getenv("LLM_MODEL", LLM_MODEL),
    )
    indexes = {
        "alias_map": alias_map,
        "inverted_index": inverted,
        "top_k_fields": MAX_SCHEMA_FIELDS,
        "examples": [],
    }
    return schema_info, indexes, graph, client


def _process_query(question: str, schema_info, indexes, graph, client, verbose: bool = True):
    """处理单条查询并打印完整结果。"""
    result = generate_sql_for_question(question, schema_info, indexes, graph, client)

    if verbose:
        ctx = result.get("schema_context", {})
        keywords = ctx.get("matched_keywords", [])
        tables = ctx.get("tables", [])
        joins = result.get("join_edges", [])

        print(f"\n{'─'*50}")
        print(f"  Query:    {result['question']}")
        print(f"  SQL:      {result['predicted_sql']}")
        print(f"  Latency:  {result['latency']:.3f}s")
        if keywords:
            print(f"  Keywords: {keywords[:8]}")
        if tables:
            print(f"  Tables:   {tables}")
        if joins:
            for e in joins:
                print(f"  JOIN:     {e['from']} -> {e['to']}")

        # 执行 + 润色
        if result["predicted_sql"] and "SELECT 1" not in result["predicted_sql"]:
            exec_r = execute_sql(str(DB_PATH), result["predicted_sql"])
            if exec_r.get("success"):
                rows = exec_r.get("rows", [])
                cols = exec_r.get("columns", [])
                print(f"  Result:   {len(rows)} row(s)")
                if rows and len(rows) <= 10:
                    for row in rows:
                        print(f"    {row}")
                elif rows:
                    for row in rows[:3]:
                        print(f"    {row}")
                    print(f"    ... ({len(rows) - 3} more)")

                answer = polish_answer(result["question"], exec_r)
                print(f"\n  Answer: {answer}")
            else:
                print(f"  Exec Error: {exec_r.get('error', 'unknown')}")

        if result.get("error"):
            print(f"  Error: {result['error']}")
        print(f"{'─'*50}")

    return result


def mode_interactive():
    """交互式查询模式。"""
    schema_info, indexes, graph, client = _load_context()

    # 加载示例
    sample_queries = []
    if VALIDATION_FILE.exists():
        records = load_test_queries(str(VALIDATION_FILE))
        sample_queries = [r["query"] for r in records[:10]]

    print("\n" + "=" * 50)
    print("  Interactive Query Mode")
    print("  Type your question, 'examples' to list, 'quit' to exit")
    print("=" * 50)

    while True:
        try:
            user_input = input("\nQuery> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break
        if user_input.lower() == "examples":
            for i, q in enumerate(sample_queries, 1):
                print(f"  [{i}] {q}")
            continue
        if user_input.isdigit() and 1 <= int(user_input) <= len(sample_queries):
            user_input = sample_queries[int(user_input) - 1]
            print(f"Using: {user_input}")

        _process_query(user_input, schema_info, indexes, graph, client)


def mode_single_query(question: str):
    """单次查询模式。"""
    schema_info, indexes, graph, client = _load_context()
    _process_query(question, schema_info, indexes, graph, client)


# ========== 入口 ==========

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NL2SQL 商品问答系统")
    parser.add_argument("--eval", action="store_true", help="验证集评估模式")
    parser.add_argument("--query", action="store_true", help="交互式查询模式")
    parser.add_argument("-q", type=str, default=None, help="单次查询（输入问题）")
    args = parser.parse_args()

    if args.query:
        mode_interactive()
    elif args.q:
        mode_single_query(args.q)
    elif args.eval:
        mode_eval()
    else:
        mode_submit()
