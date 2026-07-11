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
# provider: "openai" 走 OpenAI 兼容 API（三选一，通过环境变量切换）：
#           "mock"   测试用，不调模型
#           "local"  本地模型
#
# === 三种 LLM 的配置方式 ===
# DeepSeek:
#   export OPENAI_API_KEY="sk-xxx"
#   export OPENAI_BASE_URL="https://api.deepseek.com"
#   LLM_MODEL = "deepseek-chat"
#
# Gemini:
#   export OPENAI_API_KEY="你的Gemini_API_Key"
#   export OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
#   LLM_MODEL = "gemini-2.5-flash"
#
# OpenAI:
#   export OPENAI_API_KEY="sk-xxx"
#   (不设 OPENAI_BASE_URL，默认走 api.openai.com)
#   LLM_MODEL = "gpt-4o-mini"

LLM_PROVIDER = "openai"
LLM_MODEL = "deepseek-chat"  # deepseek-chat / gemini-2.5-flash / gpt-4o-mini

# ========== 功能开关 ==========
ENABLE_CACHE = True
ENABLE_VECTOR_RETRIEVAL = False
MAX_SCHEMA_FIELDS = 20     # 检索后放入 Prompt 的字段数（平衡速度与覆盖）
MAX_EXAMPLES = 5
