"""
验证集评估脚本：在验证集上运行 pipeline，生成 SQL，与 ground truth 对比计算 EM/EX/LS。

用法:
    python run_eval.py

前置条件:
    - OPENAI_API_KEY 环境变量已设置（或用 mock 测试）
    - 数据库已通过 data_loader 构建完成
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve()))

from src.config import (
    PROJECT_ROOT, DB_PATH, OUTPUT_PATH, TEAM_ID,
    LLM_PROVIDER, LLM_MODEL,
)
from src.main import run_pipeline
from src.evaluation import evaluate_predictions, print_evaluation_report
from src.llm_client import LLMClient

# 验证集路径
VALIDATION_FILE = PROJECT_ROOT / "初赛数据集" / "初赛_验证集 .jsonl"
EVAL_OUTPUT = PROJECT_ROOT / "outputs" / "predictions_val.json"

if __name__ == "__main__":
    print("=" * 60)
    print("  NL2SQL Validation Evaluation")
    print(f"  LLM: {LLM_PROVIDER} / {LLM_MODEL}")
    print("=" * 60)

    # Step 1: 在验证集上运行 pipeline
    print("\n[1/2] Running pipeline on validation set...")
    run_pipeline(
        test_file=str(VALIDATION_FILE),
        output_path=str(EVAL_OUTPUT),
    )

    # Step 2: 评估
    print("\n[2/2] Evaluating against ground truth...")
    result = evaluate_predictions(
        predictions_file=str(EVAL_OUTPUT),
        validation_file=str(VALIDATION_FILE),
        db_path=str(DB_PATH),
    )
    print_evaluation_report(result)
