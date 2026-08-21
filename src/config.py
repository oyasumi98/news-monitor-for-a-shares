import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DB_PATH = ROOT / os.getenv("DB_PATH", "market_events.db")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
MAIL_TO = os.getenv("MAIL_TO", "")
MAIL_FROM = os.getenv("MAIL_FROM", "") or SMTP_USER

MIN_SCORE_TO_EMAIL = float(os.getenv("MIN_SCORE_TO_EMAIL", "75"))
MAX_EMAIL_EVENTS = int(os.getenv("MAX_EMAIL_EVENTS", "10"))
# ============================================================
# 批量评分配置
# ============================================================

# 批量评分每次处理的新闻数量上限
# 建议值：200-500，取决于你的RSS源数量和API上下文窗口
# DeepSeek上下文窗口较大，可以设置500；Gemini建议300
BATCH_LIMIT = 300

# 如果担心token超限，可以启用时间窗口过滤
# 只处理过去24小时内的新闻
BATCH_TIME_WINDOW_HOURS = 24
