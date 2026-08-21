import sqlite3
from .config import DB_PATH

def init_db():
    """初始化数据库，创建所有表"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    # rss_items 表（原有）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rss_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE,
            published TEXT,
            source TEXT,
            title TEXT,
            url TEXT,
            summary TEXT,
            content TEXT,
            collected_at TEXT
        )
    """)
    
    # event_scores 表（新增扩展字段）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS event_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rss_item_id INTEGER,
            category TEXT,
            event_type TEXT,
            novelty REAL,
            economic_impact REAL,
            transmission REAL,
            expectation_gap REAL,
            market_sensitivity REAL,
            event_score REAL,
            direction TEXT,
            affected_assets TEXT,
            affected_industries TEXT,
            rationale TEXT,
            second_order_effects TEXT,
            risks TEXT,
            model TEXT,
            scored_at TEXT,
            
            -- ===== 以下为新增字段 =====
            source_news_ids TEXT,
            strong_linked_us_stocks TEXT,
            strong_linked_a_stocks TEXT,
            market_crowdedness TEXT,
            expectation_gap_detail TEXT,
            price_anomaly TEXT,
            validation_catalyst TEXT,
            confidence REAL,
            news_summary TEXT,
            marginal_change TEXT,
            industry_chain_logic TEXT,
            
            FOREIGN KEY (rss_item_id) REFERENCES rss_items(id)
        )
    """)
    
    # 创建索引（优化查询速度）
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_rss_item ON event_scores(rss_item_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_score ON event_scores(event_score)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_scored_at ON event_scores(scored_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rss_collected_at ON rss_items(collected_at)")
    
    con.commit()
    con.close()
    print("[DB] 数据库初始化完成")


def insert_rss(item):
    """插入RSS新闻"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO rss_items (
            guid, published, source, title, url, summary, content, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.get("guid", ""),
        item.get("published", ""),
        item.get("source", ""),
        item.get("title", ""),
        item.get("url", ""),
        item.get("summary", ""),
        item.get("content", ""),
        item.get("collected_at", "")
    ))
    con.commit()
    con.close()


def insert_score(rss_item_id, score_data):
    """插入评分（兼容旧版逐条评分）"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO event_scores (
            rss_item_id, category, event_type, novelty, economic_impact,
            transmission, expectation_gap, market_sensitivity, event_score,
            direction, affected_assets, affected_industries, rationale,
            second_order_effects, risks, model, scored_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rss_item_id,
        score_data.get("category", "other"),
        score_data.get("event_type", ""),
        score_data.get("novelty", 0),
        score_data.get("economic_impact", 0),
        score_data.get("transmission", 0),
        score_data.get("expectation_gap", 50),
        score_data.get("market_sensitivity", 0),
        score_data.get("event_score", 0),
        score_data.get("direction", "unknown"),
        score_data.get("affected_assets", ""),
        score_data.get("affected_industries", ""),
        score_data.get("rationale", ""),
        score_data.get("second_order_effects", ""),
        score_data.get("risks", ""),
        score_data.get("model", "deepseek"),
        score_data.get("scored_at", "")
    ))
    con.commit()
    con.close()


def get_recent_scored(min_score=60, limit=10):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    
    rows = cur.execute("""
        SELECT 
            e.*,
            r.title, r.url, r.source, r.published, r.summary,
            COALESCE(e.news_summary, '') as news_summary,
            COALESCE(e.marginal_change, '') as marginal_change,
            COALESCE(e.industry_chain_logic, '') as industry_chain_logic,
            COALESCE(e.strong_linked_us_stocks, '[]') as strong_linked_us_stocks,
            COALESCE(e.strong_linked_a_stocks, '[]') as strong_linked_a_stocks,
            COALESCE(e.price_anomaly, '{}') as price_anomaly,
            COALESCE(e.validation_catalyst, '') as validation_catalyst,
            COALESCE(e.market_crowdedness, 'unknown') as market_crowdedness,
            COALESCE(e.expectation_gap_detail, '') as expectation_gap_detail,
            COALESCE(e.confidence, 0) as confidence
        FROM event_scores e
        JOIN rss_items r ON e.rss_item_id = r.id
        WHERE e.event_score >= ?
        ORDER BY e.event_score DESC, e.scored_at DESC
        LIMIT ?
    """, (min_score, limit)).fetchall()
    
    con.close()
    return [dict(row) for row in rows]


# ============================================================
# 批量评分专用
# ============================================================

def insert_batch_events(event, rss_item_id):
    """
    批量评分专用插入函数（由 batch_scorer 调用）
    写入所有扩展字段
    """
    import json
    from datetime import datetime
    
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    cur.execute("""
        INSERT OR REPLACE INTO event_scores (
            rss_item_id, category, event_type, novelty, economic_impact,
            transmission, expectation_gap, market_sensitivity, event_score,
            direction, affected_assets, affected_industries, rationale,
            second_order_effects, risks, model, scored_at,
            source_news_ids, strong_linked_us_stocks, strong_linked_a_stocks,
            market_crowdedness, expectation_gap_detail, price_anomaly,
            validation_catalyst, confidence, news_summary, marginal_change,
            industry_chain_logic
        ) VALUES (
            :rss_item_id, :category, :event_type, :novelty, :economic_impact,
            :transmission, :expectation_gap, :market_sensitivity, :event_score,
            :direction, :affected_assets, :affected_industries, :rationale,
            :second_order_effects, :risks, :model, :scored_at,
            :source_news_ids, :strong_linked_us_stocks, :strong_linked_a_stocks,
            :market_crowdedness, :expectation_gap_detail, :price_anomaly,
            :validation_catalyst, :confidence, :news_summary, :marginal_change,
            :industry_chain_logic
        )
    """, {
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
        "scored_at": datetime.now().isoformat(),
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
    })
    
    con.commit()
    con.close()
