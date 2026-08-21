"""
batch_scorer.py - 批量评分模式
一次性把所有新闻发给LLM，由LLM自行聚类去重
"""

import json
import sqlite3
from datetime import datetime, timezone
from .config import DB_PATH
from .db import init_db, insert_score, insert_batch_events
from .llm_client import call_deepseek, call_gemini
from .llm_prompt import make_batch_prompt
from .market_data import fetch_all_market_data, format_market_data_for_prompt


def get_unscored_news(limit=200):
    """获取未评分的新闻"""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT r.* FROM rss_items r
        LEFT JOIN event_scores e ON r.id = e.rss_item_id
        WHERE e.id IS NULL
        ORDER BY r.id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    con.close()
    return [dict(row) for row in rows]


def run_batch():
    """
    批量评分：把所有新闻发给LLM，让LLM聚类去重
    """
    init_db()
    
    # 1. 获取未评分的新闻
    items = get_unscored_news(200)
    if not items:
        print("[BATCH] 没有未评分的新闻")
        return
    
    print(f"[BATCH] 获取到 {len(items)} 条未评分新闻")
    
    # 2. 获取市场数据
    try:
        market_data_dict = fetch_all_market_data()
        market_text = format_market_data_for_prompt(market_data_dict)
    except Exception as e:
        print(f"[BATCH] 获取市场数据失败: {e}")
        market_text = "unknown"
    
    # 3. 构建批量提示词
    current_time = datetime.now(timezone.utc).isoformat()
    prompt = make_batch_prompt(items, current_time, market_text)
    
    # 4. 调用LLM
    try:
        if DEEPSEEK_API_KEY:
            raw = call_deepseek_batch(prompt)
            model = "deepseek-batch"
        elif GEMINI_API_KEY:
            raw = call_gemini_batch(prompt)
            model = "gemini-batch"
        else:
            raise RuntimeError("未配置API Key")
    except Exception as e:
        print(f"[BATCH] LLM调用失败: {e}")
        return
    
    # 5. 解析JSON
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        events = json.loads(raw)
        if not isinstance(events, list):
            events = [events]
    except json.JSONDecodeError as e:
        print(f"[BATCH] JSON解析失败: {e}")
        print(f"[BATCH] 原始返回: {raw[:500]}...")
        return
    
    # 6. 保存结果
    print(f"[BATCH] LLM返回 {len(events)} 个聚类事件")
    
    for event in events:
        # 为缺失字段补默认值
        event = fill_defaults(event)
        # 保存到数据库
        insert_batch_event(event, items)
        # 打印日志
        score = event.get("event_score", 0)
        summary = event.get("news_summary", "")[:50]
        print(f"[BATCH] {score:.0f} | {summary}")
    
    print(f"[BATCH] 完成，共处理 {len(events)} 个事件")


def call_deepseek_batch(prompt):
    """调用DeepSeek批量模式"""
    import requests
    from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    
    r = requests.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                 "Content-Type": "application/json"},
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        },
        timeout=120
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def call_gemini_batch(prompt):
    """调用Gemini批量模式"""
    import requests
    from .config import GEMINI_API_KEY, GEMINI_MODEL
    
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
        },
        timeout=120
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def fill_defaults(event):
    """补全缺失字段"""
    defaults = {
        "event_cluster": "",
        "source_news_ids": [],
        "is_repeat": False,
        "is_valid_time_window": True,
        "news_summary": "",
        "marginal_change": "",
        "category": "other",
        "industry_chain_logic": "",
        "strong_linked_us_stocks": [],
        "strong_linked_a_stocks": [],
        "market_crowdedness": "unknown",
        "expectation_gap": "unknown",
        "expectation_gap_detail": "",
        "price_anomaly": {"stock": "", "change_pct": 0, "volume": "", "suspected_reason": "", "confidence": None},
        "speaker": {"name": None, "role": None, "statement_type": None, "core_view": None},
        "validation_catalyst": None,
        "novelty": 0,
        "economic_impact": 0,
        "transmission": 0,
        "expectation_gap_score": 0,
        "market_sensitivity": 0,
        "event_score": 0,
        "direction": "unknown",
        "rationale": "",
        "second_order_effects": "",
        "risks": "",
        "confidence": 0
    }
    for key, default in defaults.items():
        if key not in event or event[key] is None:
            event[key] = default
    return event


def insert_batch_event(event, all_items):
    """将聚类事件保存到数据库（简化版，与现有表结构兼容）"""
    import sqlite3
    from .config import DB_PATH
    
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    # 获取第一条关联新闻的ID（用于关联）
    source_ids = event.get("source_news_ids", [])
    first_id = source_ids[0] if source_ids else None
    
    if first_id is None:
        # 尝试通过标题匹配
        summary = event.get("news_summary", "")
        cur.execute("SELECT id FROM rss_items WHERE title LIKE ? LIMIT 1", (f"%{summary[:20]}%",))
        row = cur.fetchone()
        if row:
            first_id = row[0]
    
    if first_id is None:
        con.close()
        return
    
    # 构建评分数据（与现有 event_scores 表结构对齐）
    score_data = {
        "rss_item_id": first_id,
        "category": event.get("category", "other"),
        "event_type": event.get("event_cluster", "")[:100],
        "novelty": float(event.get("novelty", 0)),
        "economic_impact": float(event.get("economic_impact", 0)),
        "transmission": float(event.get("transmission", 0)),
        "expectation_gap": float(event.get("expectation_gap_score", 50)),
        "market_sensitivity": float(event.get("market_sensitivity", 0)),
        "event_score": float(event.get("event_score", 0)),
        "direction": event.get("direction", "unknown"),
        "affected_assets": "",  # 已废弃，保留为空
        "affected_industries": "",  # 已废弃，保留为空
        "rationale": event.get("rationale", ""),
        "second_order_effects": event.get("second_order_effects", ""),
        "risks": event.get("risks", ""),
        "model": "batch",
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "source_news_ids": json.dumps(source_ids),
        "strong_linked_us_stocks": json.dumps(event.get("strong_linked_us_stocks", [])),
        "strong_linked_a_stocks": json.dumps(event.get("strong_linked_a_stocks", [])),
        "market_crowdedness": event.get("market_crowdedness", "unknown"),
        "expectation_gap_detail": event.get("expectation_gap_detail", ""),
        "price_anomaly": json.dumps(event.get("price_anomaly", {})),
        "validation_catalyst": event.get("validation_catalyst", ""),
        "confidence": float(event.get("confidence", 0)),
    }
    
    # 插入评分（如果已存在则更新）
    cur.execute("""
        INSERT OR REPLACE INTO event_scores (
            rss_item_id, category, event_type, novelty, economic_impact,
            transmission, expectation_gap, market_sensitivity, event_score,
            direction, affected_assets, affected_industries, rationale,
            second_order_effects, risks, model, scored_at,
            source_news_ids, strong_linked_us_stocks, strong_linked_a_stocks,
            market_crowdedness, expectation_gap_detail, price_anomaly,
            validation_catalyst, confidence
        ) VALUES (
            :rss_item_id, :category, :event_type, :novelty, :economic_impact,
            :transmission, :expectation_gap, :market_sensitivity, :event_score,
            :direction, :affected_assets, :affected_industries, :rationale,
            :second_order_effects, :risks, :model, :scored_at,
            :source_news_ids, :strong_linked_us_stocks, :strong_linked_a_stocks,
            :market_crowdedness, :expectation_gap_detail, :price_anomaly,
            :validation_catalyst, :confidence
        )
    """, score_data)
    
    con.commit()
    con.close()


if __name__ == "__main__":
    run_batch()
