import sqlite3
import json
import os
import requests
from datetime import datetime, timezone, timedelta

from .config import DB_PATH


# ============================================================
# 0. 数据库初始化
# ============================================================

def init_db():
    """初始化数据库，创建 rss_items 和 event_scores 表"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

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
            FOREIGN KEY (rss_item_id) REFERENCES rss_items(id)
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_rss_item ON event_scores(rss_item_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_score ON event_scores(event_score)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_scored_at ON event_scores(scored_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rss_collected_at ON rss_items(collected_at)")

    con.commit()
    con.close()
    print("[DB] 数据库初始化完成")


# ============================================================
# 插入函数
# ============================================================

def insert_rss(item):
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
    """插入评分"""
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


def get_recent_scored(min_score=0, limit=100):
    """获取评分事件，默认不设门槛"""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute("""
        SELECT 
            e.*,
            r.title, r.url, r.source, r.published, r.summary
        FROM event_scores e
        JOIN rss_items r ON e.rss_item_id = r.id
        WHERE e.event_score >= ?
        ORDER BY e.event_score DESC, e.scored_at DESC
        LIMIT ?
    """, (min_score, limit)).fetchall()
    con.close()
    return [dict(row) for row in rows]


# ============================================================
# 获取过去24小时新闻
# ============================================================

def get_recent_news(hours=24):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute("""
        SELECT id, guid, published, source, title, url, summary, content, collected_at
        FROM rss_items
        ORDER BY id DESC
    """).fetchall()
    con.close()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    result = []
    for row in rows:
        item = dict(row)
        dt = parse_datetime(item.get("published"))
        if dt is None:
            dt = parse_datetime(item.get("collected_at"))
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        if dt < cutoff:
            continue
        result.append(item)
    return result


def parse_datetime(value):
    if not value:
        return None
    value = str(value).strip()
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


# ============================================================
# DeepSeek 调用
# ============================================================

def call_deepseek(prompt):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_tokens": 4000
    }
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=120
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def extract_json(text):
    if not text:
        return None
    text = text.strip()
    print(f"[DEBUG] extract_json 输入长度: {len(text)}")
    print(f"[DEBUG] 前 500 字符: {text[:500]}")
    print(f"[DEBUG] 后 500 字符: {text[-500:]}")

    # 移除 markdown 代码块
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            lines = lines[1:]
            if lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

    # 尝试提取最外层 JSON（从第一个 { 到最后一个 }）
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start:end+1]
        # 尝试解析
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            print(f"[DEBUG] 候选 JSON 解析失败: {e}")
            # 尝试修复常见问题：尾随逗号
            import re
            # 移除尾随逗号
            fixed = re.sub(r',\s*([}\]])', r'\1', candidate)
            try:
                return json.loads(fixed)
            except:
                pass

    # 如果还是失败，保存原始内容到文件以便调试（在 Actions 中可通过 artifacts 下载）
    try:
        with open("debug_raw.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("[DEBUG] 原始返回已保存到 debug_raw.txt")
    except:
        pass

    return None

# ============================================================
# 构建批量提示词（强制输出至少5个事件）
# ============================================================

def make_batch_prompt(items, current_time, market_text):
    news_blocks = []
    for i, item in enumerate(items[:150]):
        # ---- 关键修复：安全处理新闻内容中的 { 和 } ----
        def safe_str(s):
            if s is None:
                return ""
            # 替换 { 和 } 为不可见字符，防止 f-string 解析错误
            return str(s).replace("{", "【").replace("}", "】")
        
        news_blocks.append(f"""
================ NEWS {i} ================

NEWS_ID: {safe_str(item.get("id", ""))}
SOURCE: {safe_str(item.get("source", ""))}
PUBLISHED: {safe_str(item.get("published", ""))}
TITLE: {safe_str(item.get("title", ""))}
SUMMARY: {safe_str(item.get("summary", ""))}
CONTENT: {safe_str(item.get("content", ""))[:2000]}
URL: {safe_str(item.get("url", ""))}

===========================================
""")
    news_text = "\n".join(news_blocks)

    return f"""
你是一名全球宏观、科技产业、政策和事件驱动投资领域的资深策略分析师。

当前时间：{current_time}

============================================================
你的核心任务
============================================================

从过去24小时新闻中，识别出所有具有潜在预期差的事件。

**你必须输出至少5个、最多20个候选事件。**

不要只选1个。如果有多个事件有预期差，全部列出。

筛选标准（按重要性排序）：
1. 预期差：市场定价 vs 事件实际含义的差距
2. 边际变化：相比昨天，今天发生了什么新的事实
3. 产业链传导：能否影响至少1层产业链（不强制2层）
4. A股映射：优先选择有明确A股映射的事件，但**允许使用行业ETF或概念股作为替代**

重点关注"异常"信号：
- 价格异常：某股票突然大涨/大跌但没有对应新闻
- 基本面异常：冷门行业公司突然获得大订单
- 政策异常：原本不可能的政策方向突然松动
- 人物言论异常：一贯保守的官员/CEO突然释放激进信号
- 产业链异常：上游产能突然收缩/扩张

============================================================
输出格式（必须至少5个事件）
============================================================

{{
    "signal": "MULTIPLE_CANDIDATES",
    "candidates": [
        {{
            "title": "事件标题",
            "category": "macro|policy|technology|company|industry_chain|market_event",
            "news_summary": "一句话总结",
            "what_changed": "发生了什么边际变化",
            "expectation_gap": "high|medium|low",
            "expectation_gap_detail": "具体预期差描述",
            "abnormality_score": 0-100,
            "abnormality_reason": "为什么认为异常",
            "a_share_idea": {{
                "name": "公司或ETF名称",
                "ticker": "股票或ETF代码",
                "type": "stock|ETF",
                "logic": "投资逻辑",
                "directness": "DIRECT|INDIRECT|SECOND_ORDER"
            }},
            "us_reference": [],
            "industry_chain_logic": "产业链传导",
            "investment_thesis": "投资要点",
            "key_risks": ["风险1", "风险2"],
            "catalyst_timeline": "未来催化剂时间"
        }}
    ]
}}

如果没有任何事件有预期差：
{{"signal": "NO_CLEAR_EDGE"}}

============================================================
硬性要求
============================================================

1. **必须输出至少5个事件**，最多20个
2. 按预期差从高到低排序
3. 优先选择有A股映射的事件，但**不要因为A股映射不明确就完全排除**
4. 如果某事件已经被市场充分定价，排除
5. 不要只输出"最大"的新闻，要输出"最异常"的新闻
6. 只返回JSON

============================================================
过去24小时新闻
============================================================

{news_text}
"""



# ============================================================
# 保存单个事件
# ============================================================

def save_single_event(event, rss_item_id):
    """将单个候选事件存入数据库"""
    score_data = {
        "category": event.get("category", "other"),
        "event_type": event.get("title", "")[:100],
        "novelty": event.get("abnormality_score", 0),
        "economic_impact": 50,
        "transmission": 50,
        "expectation_gap": 50,
        "market_sensitivity": 50,
        "event_score": event.get("abnormality_score", 0),
        "direction": "unknown",
        "affected_assets": json.dumps({
            "a_share": event.get("a_share_idea", {}),
            "us_reference": event.get("us_reference", []),
            "expectation_gap_detail": event.get("expectation_gap_detail", ""),
            "industry_chain_logic": event.get("industry_chain_logic", ""),
            "key_risks": event.get("key_risks", []),
            "catalyst_timeline": event.get("catalyst_timeline", "")
        }, ensure_ascii=False),
        "affected_industries": event.get("category", ""),
        "rationale": event.get("investment_thesis", ""),
        "second_order_effects": "",
        "risks": "\n".join(event.get("key_risks", [])),
        "model": "deepseek-multi-candidate",
        "scored_at": datetime.now(timezone.utc).isoformat()
    }
    insert_score(rss_item_id, score_data)


def find_news_id_for_event(event, items):
    """尝试为事件匹配对应的新闻ID"""
    # 方法1：通过标题关键词匹配
    title_keywords = event.get("title", "")[:30].strip()
    if title_keywords and len(title_keywords) > 5:
        for item in items:
            item_title = item.get("title", "")
            if title_keywords.lower() in item_title.lower():
                return item.get("id")
    
    # 方法2：通过事件聚类名称匹配
    cluster = event.get("category", "")
    if cluster and len(cluster) > 3:
        for item in items:
            item_title = item.get("title", "")
            if cluster.lower() in item_title.lower():
                return item.get("id")
    
    # 方法3：返回第一条新闻的ID（兜底）
    if items:
        return items[0].get("id")
    
    return None


# ============================================================
# 保存 ONE BIG EVENT（兼容旧模式）
# ============================================================

def save_one_big_event(result):
    """把 ONE BIG EVENT 转换成 event_scores 表结构"""
    event = result.get("event", {})
    scores = result.get("scores", {})
    idea = event.get("a_share_idea", {})

    source_ids = event.get("source_news_ids", [])
    rss_item_id = None

    if source_ids:
        try:
            rss_item_id = int(source_ids[0])
        except Exception:
            pass

    if rss_item_id is None:
        items = get_recent_news(hours=24)
        if items:
            title_keywords = event.get("title", "")[:30].strip()
            if title_keywords and len(title_keywords) > 5:
                for item in items:
                    if title_keywords.lower() in item.get("title", "").lower():
                        rss_item_id = item.get("id")
                        break
            if rss_item_id is None:
                rss_item_id = items[0].get("id")

    if rss_item_id is None:
        print("[BATCH] 没有有效rss_item_id，跳过数据库保存")
        return

    score_data = {
        "category": event.get("category", "other"),
        "event_type": event.get("event_cluster", "")[:100],
        "novelty": scores.get("novelty", 0),
        "economic_impact": scores.get("fundamental_impact", 0),
        "transmission": scores.get("transmission", 0),
        "expectation_gap": scores.get("expectation_gap", 50),
        "market_sensitivity": scores.get("market_mispricing", 0),
        "event_score": scores.get("investment_score", 0),
        "direction": event.get("direction", "unknown"),
        "affected_assets": json.dumps({
            "a_share": idea,
            "us_reference": event.get("us_reference", []),
            "expectation_gap_detail": event.get("expectation_gap_detail", ""),
            "key_catalysts": event.get("key_catalysts", []),
            "future_1_4_weeks": event.get("future_1_4_weeks", {})
        }, ensure_ascii=False),
        "affected_industries": event.get("category", ""),
        "rationale": event.get("investment_thesis", ""),
        "second_order_effects": event.get("future_1_4_weeks", {}).get("base_case", ""),
        "risks": "\n".join(event.get("key_risks", [])),
        "model": "deepseek-one-big-event",
        "scored_at": datetime.now(timezone.utc).isoformat()
    }

    insert_score(rss_item_id, score_data)
    print(f"[BATCH] ONE BIG EVENT 已保存，A股：{idea.get('name', '')} ({idea.get('ticker', '')})")


# ============================================================
# 主函数
# ============================================================
# ============================================================
# 获取过去24小时新闻
# ============================================================

def get_recent_news(hours=24, limit=None):
    """
    从 rss_items 表中获取过去 hours 小时内的新闻
    
    Args:
        hours: 时间范围（小时），默认24
        limit: 最大返回条数，默认 None 表示不限制
    
    Returns:
        list: 新闻列表，每个元素为 dict
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    
    # 计算时间阈值
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_str = cutoff.isoformat()
    
    # 构建查询
    query = """
        SELECT id, guid, published, source, title, url, summary, content, collected_at
        FROM rss_items
        WHERE collected_at >= ?
        ORDER BY collected_at DESC
    """
    params = [cutoff_str]
    
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    
    rows = cur.execute(query, params).fetchall()
    con.close()
    
    return [dict(row) for row in rows]
    
def run_batch(market_text="unknown"):
    print("[BATCH] ===== GLOBAL MARKET SURPRISE DETECTOR =====")
    init_db()

    now = datetime.now(timezone.utc)
    print(f"[BATCH] 当前UTC时间：{now.isoformat()}")
    items = get_recent_news(hours=24)
    print(f"[BATCH] 获取新闻：{len(items)}条")
    if not items:
        print("[BATCH] 没有新闻")
        return None

    if market_text != "unknown":
        print("[BATCH] 使用最新市场数据")
    else:
        print("[BATCH] 市场数据不可用")

    prompt = make_batch_prompt(items, now.isoformat(), market_text)
    print(f"[BATCH] Prompt长度：{len(prompt)}字符")

    print("[BATCH] 调用DeepSeek...")
    try:
        raw = call_deepseek(prompt)
    except Exception as e:
        print(f"[BATCH] DeepSeek调用失败：{e}")
        return None

    print(f"[BATCH] LLM返回长度：{len(raw)}字符")
    result = extract_json(raw)
    if not result:
        print("[BATCH] JSON解析失败，尝试从返回中提取候选...")
    # 可以尝试另一种解析方式，比如正则提取多个 JSON 对象
    # 但最简单的是直接返回 None，并打印提示
        print("[BATCH] 建议检查 debug_raw.txt 查看原始返回")
        return None
    
    if result.get("signal") == "NO_CLEAR_EDGE":
        print("[BATCH] 没有识别到有预期差的事件")
        return None

    # ---- 兼容两种模式 ----
    if result.get("signal") == "ONE_BIG_EVENT":
        print("[BATCH] 使用 ONE_BIG_EVENT 模式")
        save_one_big_event(result)
        
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        count = cur.execute("SELECT COUNT(*) FROM event_scores").fetchone()[0]
        print(f"[BATCH] 验证：event_scores 表中当前共有 {count} 条记录")
        con.close()
        return result

    if result.get("signal") != "MULTIPLE_CANDIDATES":
        print(f"[BATCH] 信号格式异常，预期 MULTIPLE_CANDIDATES，实际: {result.get('signal')}")
        return None

    candidates = result.get("candidates", [])
    if not candidates:
        print("[BATCH] 候选列表为空")
        return None

    print(f"[BATCH] 共识别出 {len(candidates)} 个候选事件")
    candidates.sort(key=lambda x: x.get("abnormality_score", 0), reverse=True)

    saved_count = 0
    for idx, evt in enumerate(candidates):
        rss_item_id = find_news_id_for_event(evt, items)
        if rss_item_id is None:
            print(f"[BATCH] 跳过保存，无关联新闻ID：{evt.get('title', '')[:30]}")
            continue
        save_single_event(evt, rss_item_id)
        saved_count += 1
        print(f"[BATCH] {idx+1}. {evt.get('title', '')[:60]} - 异常分：{evt.get('abnormality_score', 0)}")

    print(f"[BATCH] 成功保存 {saved_count}/{len(candidates)} 个事件")

    # 验证
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        count = cur.execute("SELECT COUNT(*) FROM event_scores").fetchone()[0]
        print(f"[BATCH] 验证：event_scores 表中当前共有 {count} 条记录")
        con.close()
    except Exception as e:
        print(f"[BATCH] 验证查询失败：{e}")

    return result
