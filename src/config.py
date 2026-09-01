import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# API配置
# ============================================================

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ============================================================
# 邮件配置
# ============================================================

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
MAIL_TO = os.getenv("MAIL_TO")
MAIL_FROM = os.getenv("MAIL_FROM")

MIN_SCORE_TO_EMAIL = int(os.getenv("MIN_SCORE_TO_EMAIL", 0))
MAX_EMAIL_EVENTS = int(os.getenv("MAX_EMAIL_EVENTS", 100))  # 调大，便于取更多候选

# ============================================================
# 数据库配置
# ============================================================

DB_PATH = os.getenv("DB_PATH", "market_events.db")

# ============================================================
# 批量评分配置（新增）
# ============================================================

# 每次批量评分处理的新闻数量上限
# DeepSeek 推荐 300-500，Gemini 推荐 500-1000
BATCH_LIMIT = int(os.getenv("BATCH_LIMIT", 500))

# 时间窗口：只处理过去N小时的新闻
# 设为 0 表示不限制
BATCH_TIME_WINDOW_HOURS = int(os.getenv("BATCH_TIME_WINDOW_HOURS", 24))
