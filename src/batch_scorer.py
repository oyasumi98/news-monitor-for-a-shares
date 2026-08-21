import sqlite3
import json
import requests
from datetime import datetime, timedelta, timezone
from . import config
from .db import init_db
from .llm_prompt import make_batch_prompt


def get_unscored_news(limit=None):
    """
    获取未评分的新闻
    """
    if limit is None:
        limit = config.BATCH_LIMIT

    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row

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


def call_deepseek_batch(prompt):
    """调用DeepSeek批量模式"""
    r = requests.post(
        f"{config.DEEPSEEK_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
                 "Content-Type": "application/json"},
        json={
            "model": config.DEEPSEEK_MODEL,
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
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
        params={"key": config.GEMINI_API_KEY},
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
        "expectation_gap_score": 50,
        "market_sensitivity": 0,
        "event_score": 0,
        "direction": "unknown",
        "rationale": "",
        "second_order_effects": "",
        "risks": "",
        "confidence": 0,
        "affected_assets": "",
        "affected_industries": "",
    }
    for key, default in defaults.items():
        if key not in event or event[key] is None:
            event[key] = default
    return event


def insert_batch_event(event, all_items):
    """将聚类事件保存到数据库"""
    con = sqlite3.connect(config.DB_PATH)
    cur = con.cursor()

    # 尝试匹配新闻ID
    rss_item_id = _get_event_rss_item_id(event, all_items, cur)
    if rss_item_id is None:
        con.close()
        return False

    score_data = {
        "rss_item_id": rss_item_id,
        "category": event.get("category", "other"),
        "event_type": event.get("event_cluster", "")[:100],
        "novelty": float(event.get("novelty", 0)),
        "economic_impact": float(event.get("economic_impact", 0)),
        "transmission": float(event.get("transmission", 0)),
        "expectation_gap": float(event.get("expectation_gap_score", 50)),
        "market_sensitivity": float(event.get("market_sensitivity", 0)),
        "event_score": float(event.get("event_score", 0)),
        "direction": event.get("direction", "unknown"),
        "affected_assets": event.get("affected_assets", ""),
        "affected_industries": event.get("affected_industries", ""),
        "rationale": event.get("rationale", ""),
        "second_order_effects": event.get("second_order_effects", ""),
        "risks": event.get("risks", ""),
        "model": "batch",
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "source_news_ids": json.dumps(event.get("source_news_ids", [])),
        "strong_linked_us_stocks": json.dumps(event.get("strong_linked_us_stocks", [])),
        "strong_linked_a_stocks": json.dumps(event.get("strong_linked_a_stocks", [])),
        "market_crowdedness": event.get("market_crowdedness", "unknown"),
        "expectation_gap_detail": event.get("expectation_gap_detail", ""),
        "price_anomaly": json.dumps(event.get("price_anomaly", {})),
        "validation_catalyst": event.get("validation_catalyst", ""),
        "confidence": float(event.get("confidence", 0)),
        "news_summary": event.get("news_summary", ""),
        "marginal_change": event.get("marginal_change", ""),
        "industry_chain_logic": event.get("industry_chain_logic", ""),
    }

    # 检查是否已存在
    cur.execute("SELECT id FROM event_scores WHERE rss_item_id = ?", (rss_item_id,))
    existing = cur.fetchone()
    if existing:
        cur.execute("""
            UPDATE event_scores SET
                category = :category,
                event_type = :event_type,
                novelty = :novelty,
                economic_impact = :economic_impact,
                transmission = :transmission,
                expectation_gap = :expectation_gap,
                market_sensitivity = :market_sensitivity,
                event_score = :event_score,
                direction = :direction,
                affected_assets = :affected_assets,
                affected_industries = :affected_industries,
                rationale = :rationale,
                second_order_effects = :second_order_effects,
                risks = :risks,
                model = :model,
                scored_at = :scored_at,
                source_news_ids = :source_news_ids,
                strong_linked_us_stocks = :strong_linked_us_stocks,
                strong_linked_a_stocks = :strong_linked_a_stocks,
                market_crowdedness = :market_crowdedness,
                expectation_gap_detail = :expectation_gap_detail,
                price_anomaly = :price_anomaly,
                validation_catalyst = :validation_catalyst,
                confidence = :confidence,
                news_summary = :news_summary,
                marginal_change = :marginal_change,
                industry_chain_logic = :industry_chain_logic
            WHERE rss_item_id = :rss_item_id
        """, score_data)
    else:
        columns = _get_table_columns(cur)
        insert_data = {k: v for k, v in score_data.items() if k in columns}
        placeholders = ", ".join([f":{k}" for k in insert_data.keys()])
        columns_str = ", ".join(insert_data.keys())
        cur.execute(f"INSERT INTO event_scores ({columns_str}) VALUES ({placeholders})", insert_data)

    con.commit()
    con.close()
    return True


def _get_table_columns(cur):
    """获取 event_scores 表的列名列表"""
    cur.execute("PRAGMA table_info(event_scores)")
    return [row[1] for row in cur.fetchall()]


def _get_event_rss_item_id(event, all_items, cur):
    """匹配事件对应的新闻ID"""
    source_ids = event.get("source_news_ids", [])
    if source_ids and isinstance(source_ids, list) and len(source_ids) > 0:
        first_id = source_ids[0]
        if isinstance(first_id, int) and first_id < len(all_items):
            return all_items[first_id].get("id")
        cur.execute("SELECT id FROM rss_items WHERE id = ?", (first_id,))
        row = cur.fetchone()
        if row:
            return row[0]

    summary = event.get("news_summary", "")
    if summary:
        keyword = summary[:30].strip()
        if len(keyword) > 5:
            cur.execute("SELECT id FROM rss_items WHERE title LIKE ? LIMIT 1", (f"%{keyword}%",))
            row = cur.fetchone()
            if row:
                return row[0]

    cluster = event.get("event_cluster", "")
    if cluster:
        keyword = cluster[:20].strip()
        if len(keyword) > 3:
            cur.execute("SELECT id FROM rss_items WHERE title LIKE ? LIMIT 1", (f"%{keyword}%",))
            row = cur.fetchone()
            if row:
                return row[0]

    return None


def run_batch(market_text=None, limit=None):
    """
    批量评分：把所有新闻发给LLM，让LLM聚类去重
    """
    print("[BATCH] ===== 进入 run_batch 函数 =====")

    if limit is None:
        limit = config.BATCH_LIMIT
    print(f"[BATCH] 本次处理上限: {limit} 条")

    items = get_unscored_news(limit)
    if not items:
        print("[BATCH] 没有未评分的新闻")
        return

    print(f"[BATCH] 获取到 {len(items)} 条未评分新闻")

    if market_text is None:
        print("[BATCH] 尝试获取市场数据...")
        try:
            from .market_data import fetch_all_market_data, format_market_data_for_prompt
            market_data_dict = fetch_all_market_data()
            market_text = format_market_data_for_prompt(market_data_dict)
        except Exception as e:
            print(f"[BATCH] 获取市场数据失败: {e}")
            market_text = "unknown"
    else:
        print("[BATCH] 使用外部传入的市场数据")

    current_time = datetime.now(timezone.utc).isoformat()
    prompt = make_batch_prompt(items, current_time, market_text)
    print(f"[BATCH] 提示词构建完成，长度: {len(prompt)} 字符")

    try:
        if config.DEEPSEEK_API_KEY:
            raw = call_deepseek_batch(prompt)
            model = "deepseek-batch"
            print("[BATCH] DeepSeek 调用成功")
        elif config.GEMINI_API_KEY:
            raw = call_gemini_batch(prompt)
            model = "gemini-batch"
            print("[BATCH] Gemini 调用成功")
        else:
            raise RuntimeError("未配置API Key")
    except Exception as e:
        print(f"[BATCH] LLM调用失败: {e}")
        return

    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    print(f"[BATCH] LLM原始返回长度: {len(raw)} 字符")
    print(f"[BATCH] 返回内容预览: {raw[:200]}...")

    try:
        events = json.loads(raw)
        if not isinstance(events, list):
            events = [events]
    except json.JSONDecodeError as e:
        print(f"[BATCH] JSON解析失败: {e}")
        print(f"[BATCH] 原始返回: {raw[:500]}...")
        return

    print(f"[BATCH] LLM返回 {len(events)} 个聚类事件")

    saved_count = 0
    for event in events:
        event = fill_defaults(event)
        success = insert_batch_event(event, items)
        if success:
            saved_count += 1
            score = event.get("event_score", 0)
            summary = event.get("news_summary", "")[:50]
            print(f"[BATCH] {score:.0f} | {summary}")
        else:
            print(f"[BATCH] 跳过: {event.get('news_summary', '')[:30]} (无法匹配新闻)")

    print(f"[BATCH] 完成，成功保存 {saved_count}/{len(events)} 个事件")


if __name__ == "__main__":
    run_batch()
