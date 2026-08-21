from .config import DB_PATH, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, GEMINI_API_KEY, GEMINI_MODEL, BATCH_LIMIT
from .db import init_db

def get_unscored_news(limit=None):
    """
    获取未评分的新闻
    
    Args:
        limit: 数量限制，默认从 config.BATCH_LIMIT 读取
    """
    if limit is None:
        limit = BATCH_LIMIT
    
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    
    # 同时限制时间窗口（过去24小时）
    from datetime import datetime, timedelta
    time_threshold = (datetime.now() - timedelta(hours=24)).isoformat()
    
    rows = con.execute("""
        SELECT r.* FROM rss_items r
        LEFT JOIN event_scores e ON r.id = e.rss_item_id
        WHERE e.id IS NULL
          AND r.collected_at >= ?
        ORDER BY r.collected_at DESC
        LIMIT ?
    """, (time_threshold, limit)).fetchall()
    con.close()
    return [dict(row) for row in rows]

def run_batch(market_text=None, limit=None):
    """批量评分"""
    if limit is None:
        limit = BATCH_LIMIT
    
    # ... 其余代码不变 ...
    items = get_unscored_news(limit)
    # ...
