"""
交互式查询脚本：输入自然语言问题，查看生成的 SQL、执行结果和耗时。

用法:
    python run_query.py

输入你的问题后按回车，系统会显示:
    - 检索到的相关表/字段
    - JOIN 路径
    - 生成的 SQL
    - 执行结果
    - 延迟
输入 'quit' 或 'exit' 退出。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve()))

from src.config import DB_PATH, PROJECT_ROOT
from src.schema_parser import parse_sqlite_schema
from src.index_builder import build_all_indexes, load_index
from src.schema_graph import build_schema_graph
from src.llm_client import LLMClient
from src.sql_generator import generate_sql_for_question
from src.sql_executor import execute_sql
from src.data_loader import load_test_queries


def load_or_build_indexes(schema_info: dict) -> dict:
    """加载已有索引，或重新构建。"""
    processed = PROJECT_ROOT / "data" / "processed"
    alias_path = processed / "alias_map.json"
    inverted_path = processed / "inverted_index.json"

    if alias_path.exists() and inverted_path.exists():
        return {
            "alias_map": load_index(str(alias_path)),
            "inverted_index": load_index(str(inverted_path)),
        }
    else:
        return build_all_indexes(schema_info)


def load_or_build_graph(schema_info: dict) -> dict:
    """加载/构建表关系图。"""
    return build_schema_graph(schema_info)


def run_interactive():
    """交互式查询主循环。"""
    import os
    from src.config import LLM_PROVIDER, LLM_MODEL

    print("=" * 60)
    print("  NL2SQL Interactive Query")
    print(f"  LLM: {LLM_PROVIDER} / {LLM_MODEL}")
    print("  Type 'quit' to exit, 'examples' to show sample queries")
    print("=" * 60)

    # 一次性加载
    print("\nLoading schema, indexes, graph...")
    schema_info = parse_sqlite_schema(str(DB_PATH))
    indexes = load_or_build_indexes(schema_info)
    graph = load_or_build_graph(schema_info)

    llm_client = LLMClient(
        provider=os.getenv("LLM_PROVIDER", LLM_PROVIDER),
        model=os.getenv("LLM_MODEL", LLM_MODEL),
    )
    print("Ready!\n")

    # 加载示例 query
    sample_queries = _load_sample_queries()

    while True:
        try:
            user_input = input("Query> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        if user_input.lower() == "examples":
            print("\nSample queries:")
            for i, q in enumerate(sample_queries, 1):
                print(f"  [{i}] {q}")
            print()
            continue

        # 如果用户输入数字，使用对应示例
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(sample_queries):
                user_input = sample_queries[idx]
                print(f"Using: {user_input}")

        # 执行
        print()
        result = generate_sql_for_question(
            question=user_input,
            schema_info=schema_info,
            indexes=indexes,
            graph=graph,
            llm_client=llm_client,
        )

        _print_result(result)


def _print_result(result: dict):
    """格式化打印查询结果。"""
    print("─" * 50)
    print(f"Query:  {result['question']}")
    print(f"SQL:    {result['predicted_sql']}")
    print(f"Latency: {result['latency']:.3f}s")

    # 检索信息
    ctx = result.get("schema_context", {})
    tables = ctx.get("tables", [])
    fields = ctx.get("fields", [])
    keywords = ctx.get("matched_keywords", [])
    if tables:
        print(f"Tables:  {tables}")
    if keywords:
        print(f"Keywords: {keywords[:10]}")
    if fields:
        print(f"Top Fields ({len(fields)}):")
        for f in fields[:5]:
            print(f"  [{f.get('table','')}] {f.get('field','')} (score={f.get('score','?')})")

    # JOIN 信息
    join_edges = result.get("join_edges", [])
    if join_edges:
        print(f"JOINs ({len(join_edges)}):")
        for e in join_edges:
            print(f"  {e.get('from','')} → {e.get('to','')}  ON {e.get('on','')}")

    # 执行结果
    if result.get("predicted_sql") and result["predicted_sql"] != "SELECT 1;":
        exec_result = execute_sql(str(DB_PATH), result["predicted_sql"])
        if exec_result.get("success"):
            rows = exec_result.get("rows", [])
            cols = exec_result.get("columns", [])
            print(f"Result: {len(rows)} row(s)")
            if rows and len(rows) <= 20:
                print(f"  Columns: {cols}")
                for row in rows[:10]:
                    print(f"  {row}")
                if len(rows) > 10:
                    print(f"  ... ({len(rows) - 10} more rows)")
        else:
            print(f"Exec Error: {exec_result.get('error', 'unknown')}")

    # 错误信息
    if result.get("error"):
        print(f"Error: {result['error']}")

    print("─" * 50)
    print()


def _load_sample_queries() -> list[str]:
    """从验证集加载几条示例 query。"""
    validation_file = PROJECT_ROOT / "初赛数据集" / "初赛_验证集 .jsonl"
    if not validation_file.exists():
        return [
            "查询价格在 5000 到 10000 元之间，好评率大于 95% 的笔记本电脑。",
            "电池容量大于 5000mAh 的手机有哪些？",
            "哪些空调使用R32冷媒、制冷量在3500W以上，而且支持语音控制和睡眠模式？",
        ]
    queries = load_test_queries(str(validation_file))
    # 返回前 10 条作为示例
    return [q["query"] for q in queries[:10]]


if __name__ == "__main__":
    run_interactive()
