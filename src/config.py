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
# provider: "openai" 走 OpenAI 兼容 API
#           "deepseek" 直接走 DeepSeek OpenAI-compatible API
#           "mock"   测试用，不调模型
#           "local"  本地模型
#
# === 常用 LLM 配置方式 ===
# DeepSeek（推荐同学使用这种）:
#   $env:DEEPSEEK_API_KEY="sk-xxx"
#   $env:LLM_PROVIDER="deepseek"
#   $env:LLM_MODEL="deepseek-chat"
#
# DeepSeek（OpenAI-compatible 写法）:
#   $env:OPENAI_API_KEY="sk-xxx"
#   $env:OPENAI_BASE_URL="https://api.deepseek.com/v1"
#   $env:LLM_PROVIDER="openai"
#   $env:LLM_MODEL="deepseek-chat"
#
# Gemini:
#   $env:OPENAI_API_KEY="你的 Gemini API Key"
#   $env:OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
#   $env:LLM_PROVIDER="openai"
#   $env:LLM_MODEL="gemini-2.5-flash"
#
# OpenAI:
#   $env:OPENAI_API_KEY="sk-xxx"
#   Remove-Item Env:\OPENAI_BASE_URL -ErrorAction SilentlyContinue
#   $env:LLM_PROVIDER="openai"
#   $env:LLM_MODEL="gpt-5.6-luna"
LLM_PROVIDER = "openai"
LLM_MODEL = "deepseek-chat"  # deepseek-chat / gemini-2.5-flash / gpt-5.6-luna

# ========== 功能开关 ==========
ENABLE_CACHE = True
ENABLE_VECTOR_RETRIEVAL = False
MAX_SCHEMA_FIELDS = 20     # 检索后放入 Prompt 的字段数（平衡速度与覆盖）
MAX_EXAMPLES = 5
