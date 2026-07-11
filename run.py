"""
Project entry point.

Usage:
    python run.py                   submit mode on the test set
    python run.py --eval            validation evaluation
    python run.py --eval --limit 20 validation evaluation with a custom limit
    python run.py --query           interactive query mode
    python run.py -q "question"     single query mode
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ===== 加载 .env 文件（IDE 点运行也能读到 Key） =====
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                _key, _val = _key.strip(), _val.strip()
                if _key and _key not in os.environ:
                    os.environ[_key] = _val

sys.path.insert(0, str(Path(__file__).resolve()))

from src.config import (  # noqa: E402
    DB_PATH,
    LLM_MODEL,
    LLM_PROVIDER,
    MAX_SCHEMA_FIELDS,
    OUTPUT_PATH,
    PROJECT_ROOT,
    TEAM_ID,
)
from src.answer_polisher import polish_answer  # noqa: E402
from src.data_loader import load_test_queries  # noqa: E402
from src.evaluation import (  # noqa: E402
    _normalize_sql_for_compare,
    evaluate_predictions,
    print_evaluation_report,
)
from src.index_builder import load_index  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402
from src.main import run_pipeline  # noqa: E402
from src.schema_graph import build_schema_graph  # noqa: E402
from src.schema_parser import parse_sqlite_schema  # noqa: E402
from src.sql_executor import execute_sql  # noqa: E402
from src.sql_generator import generate_sql_for_question  # noqa: E402
from src.submission_writer import build_submission, format_latency, save_submission  # noqa: E402

try:
    from scripts.build_artifacts import load_runtime_artifacts  # noqa: E402
except ImportError:
    load_runtime_artifacts = None


TEST_FILE = PROJECT_ROOT / "初赛数据集" / "初赛_测试集.jsonl"
VALIDATION_FILE = PROJECT_ROOT / "初赛数据集" / "初赛_验证集 .jsonl"
EVAL_OUTPUT = PROJECT_ROOT / "outputs" / "predictions_val.json"


def _effective_llm() -> tuple[str, str]:
    return os.getenv("LLM_PROVIDER", LLM_PROVIDER), os.getenv("LLM_MODEL", LLM_MODEL)


def _load_context() -> tuple[dict, dict, dict, LLMClient]:
    print("[Loading] schema, indexes, graph...")
    schema_info = parse_sqlite_schema(str(DB_PATH))
    processed = PROJECT_ROOT / "data" / "processed"
    indexes = {
        "alias_map": load_index(str(processed / "alias_map.json")),
        "inverted_index": load_index(str(processed / "inverted_index.json")),
        "top_k_fields": MAX_SCHEMA_FIELDS,
        "examples": [],
    }
    if load_runtime_artifacts is not None:
        try:
            runtime_artifacts = load_runtime_artifacts(str(processed))
            indexes.update(runtime_artifacts)
            print(f"Runtime artifacts loaded: {', '.join(sorted(runtime_artifacts.keys()))}")
        except FileNotFoundError as exc:
            print(f"Runtime artifacts not fully built: {exc}")

    graph = indexes.get("schema_graph") or build_schema_graph(schema_info)
    provider, model = _effective_llm()
    client = LLMClient(provider=provider, model=model)
    return schema_info, indexes, graph, client


def mode_submit() -> None:
    provider, model = _effective_llm()
    print("=" * 60)
    print("  NL2SQL Submit Mode")
    print(f"  LLM: {provider} / {model}")
    print("=" * 60)
    run_pipeline(str(TEST_FILE), str(OUTPUT_PATH))
    print(f"\nDone -> {OUTPUT_PATH}")


def mode_eval(full: bool = False, limit: int | None = None) -> dict:
    n_samples = limit or (200 if full else 20)
    provider, model = _effective_llm()
    print("=" * 60)
    print("  NL2SQL Validation Evaluation (v2 structured route)")
    print(f"  LLM: {provider} / {model}")
    print(f"  Samples: {n_samples}")
    print(f"  Max Schema Fields: {MAX_SCHEMA_FIELDS}")
    print("=" * 60)

    schema_info, indexes, graph, llm_client = _load_context()
    records = load_test_queries(str(VALIDATION_FILE))[:n_samples]
    print(f"  Loaded {len(records)} validation queries")
    print(f"\n[Running] Generating SQL for {len(records)} queries...\n")

    predictions = []
    route_counts: dict[str, int] = {}
    total_stage_ms: dict[str, float] = {}

    for i, item in enumerate(records):
        question = item.get("query", "")
        gold_sql = item.get("sql", "")
        result = generate_sql_for_question(
            question=question,
            schema_info=schema_info,
            indexes=indexes,
            graph=graph,
            llm_client=llm_client,
        )
        pred_sql = result["predicted_sql"]
        latency = result["latency"]
        route = result.get("route", "unknown")
        route_counts[route] = route_counts.get(route, 0) + 1
        for key, value in (result.get("stage_timings") or {}).items():
            total_stage_ms[key] = total_stage_ms.get(key, 0.0) + float(value)

        is_match = _normalize_sql_for_compare(pred_sql) == _normalize_sql_for_compare(gold_sql)
        predictions.append(
            {
                "id": item.get("id", f"Q{i + 1:04d}"),
                "query": question,
                "predicted_sql": pred_sql,
                "lantancy": format_latency(latency),
                "error": result.get("error"),
                "route": route,
                "confidence": result.get("confidence"),
                "stage_timings": result.get("stage_timings"),
            }
        )

        status = "MATCH" if is_match else "DIFF"
        print(f" [{i + 1:3d}/{len(records)}] {status} | {route} | {latency:.2f}s | {question[:50]}...")
        if not is_match:
            print(f"   Pred: {pred_sql[:100]}")
            print(f"   Gold: {gold_sql[:100]}")

    save_submission(build_submission(TEAM_ID, predictions), str(EVAL_OUTPUT))
    result = evaluate_predictions(
        predictions_file=str(EVAL_OUTPUT),
        validation_file=str(VALIDATION_FILE),
        db_path=str(DB_PATH),
    )
    print_evaluation_report(result)

    if predictions:
        print("\nRoute Stats:")
        for route, count in sorted(route_counts.items()):
            print(f"  {route}: {count} ({count / len(predictions) * 100:.1f}%)")
        print("\nAvg Stage Timings:")
        for key, value in sorted(total_stage_ms.items()):
            print(f"  {key}: {value / len(predictions):.3f} ms")
    return result


def _process_query(question: str, schema_info: dict, indexes: dict, graph: dict, client: LLMClient) -> dict:
    result = generate_sql_for_question(question, schema_info, indexes, graph, client)
    print(f"\n{'-' * 50}")
    print(f"Query:   {result['question']}")
    print(f"Route:   {result.get('route', 'unknown')}")
    print(f"SQL:     {result['predicted_sql']}")
    print(f"Latency: {result['latency']:.3f}s")

    if result.get("predicted_sql") and "SELECT 1" not in result["predicted_sql"]:
        exec_result = execute_sql(str(DB_PATH), result["predicted_sql"])
        if exec_result.get("success"):
            rows = exec_result.get("rows", [])
            print(f"Result:  {len(rows)} row(s)")
            for row in rows[:10]:
                print(f"  {row}")
            if len(rows) > 10:
                print(f"  ... ({len(rows) - 10} more)")
            print(f"\nAnswer: {polish_answer(result['question'], exec_result)}")
        else:
            print(f"Exec Error: {exec_result.get('error', 'unknown')}")
    if result.get("error"):
        print(f"Error: {result['error']}")
    print(f"{'-' * 50}")
    return result


def mode_interactive() -> None:
    schema_info, indexes, graph, client = _load_context()
    sample_queries = []
    if VALIDATION_FILE.exists():
        sample_queries = [record["query"] for record in load_test_queries(str(VALIDATION_FILE))[:10]]

    print("\n" + "=" * 60)
    print("  Interactive Query Mode")
    print("  Type a question, 'examples' to list samples, 'quit' to exit")
    print("=" * 60)

    while True:
        try:
            user_input = input("\nQuery> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            print("Bye!")
            break
        if user_input.lower() == "examples":
            for i, query in enumerate(sample_queries, 1):
                print(f"  [{i}] {query}")
            continue
        if user_input.isdigit() and 1 <= int(user_input) <= len(sample_queries):
            user_input = sample_queries[int(user_input) - 1]
            print(f"Using: {user_input}")
        _process_query(user_input, schema_info, indexes, graph, client)


def mode_single_query(question: str) -> None:
    schema_info, indexes, graph, client = _load_context()
    _process_query(question, schema_info, indexes, graph, client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NL2SQL product QA system")
    parser.add_argument("--eval", action="store_true", help="run validation evaluation")
    parser.add_argument("--full", action="store_true", help="run all validation samples with --eval")
    parser.add_argument("--limit", type=int, default=None, help="run N validation samples with --eval")
    parser.add_argument("--query", action="store_true", help="interactive query mode")
    parser.add_argument("-q", type=str, default=None, help="single question")
    args = parser.parse_args()

    if args.eval:
        mode_eval(full=args.full, limit=args.limit)
    elif args.q:
        mode_single_query(args.q)
    elif args.query:
        mode_interactive()
    else:
        # 默认：无参数时进入交互模式（方便 IDE 点击运行）
        mode_interactive()
