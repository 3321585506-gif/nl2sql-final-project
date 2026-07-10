"""
项目入口脚本。
用法: python run.py
"""

from src.config import OUTPUT_PATH, PROJECT_ROOT
from src.main import run_pipeline


if __name__ == "__main__":
    print("NL2SQL 商品问答系统启动中...")
    default_test_file = PROJECT_ROOT / "初赛数据集" / "初赛_测试集.jsonl"
    run_pipeline(str(default_test_file), str(OUTPUT_PATH))
    print(f"预测文件已保存到: {OUTPUT_PATH}")
