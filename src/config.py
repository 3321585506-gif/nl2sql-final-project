"""
集中保存路径、模型配置、数据库配置、team_id、是否启用缓存等参数。
"""

from pathlib import Path

# ========== 路径配置 ==========
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DB_PATH = PROJECT_ROOT / "database" / "products.db"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "predictions.json"

# ========== 团队信息 ==========
TEAM_ID = "2075506812458762242"

# ========== LLM 配置 ==========
# provider: "openai" 走 OpenAI 兼容 API（DeepSeek 也走这里，设 OPENAI_BASE_URL 即可）
#           "mock"   测试用，不调模型
#           "local"  本地模型
LLM_PROVIDER = "openai"
LLM_MODEL = "deepseek-chat"  # 用 DeepSeek；如用 OpenAI 则改为 "gpt-4o-mini"

# ========== 功能开关 ==========
ENABLE_CACHE = True
ENABLE_VECTOR_RETRIEVAL = False
MAX_SCHEMA_FIELDS = 30
MAX_EXAMPLES = 5
