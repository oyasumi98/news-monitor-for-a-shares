import sqlite3
import json
import os
from datetime import datetime, timezone, timedelta

from .config import DB_PATH


# ============================================================
# 0. 数据库初始化
# ============================================================

def init_db():
    """初始化数据库，创建 rss_items 和 event_scores 表"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # rss_items 表
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

    # event_scores 表（包含 direction 字段）
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

    # 索引
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_rss_item ON event_scores(rss_item_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_score ON event_scores(event_score)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_scored_at ON event_scores(scored_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rss_collected_at ON rss_items(collected_at)")

    con.commit()
    con.close()
    print("[DB] 数据库初始化完成")


# ============================================================
# 插入RSS新闻
# ============================================================

def insert_rss(item):
    """插入RSS新闻到 rss_items 表"""
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


# ============================================================
# 插入评分
# ============================================================

def insert_score(rss_item_id, score_data):
    """插入评分到 event_scores 表"""
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


# ============================================================
# 获取最近评分的事件（供邮件发送）
# ============================================================

def get_recent_scored(min_score=60, limit=10):
    """获取评分 >= min_score 的事件，按评分降序排列"""
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
# 1. 获取过去24小时RSS新闻
# ============================================================

def get_recent_news(hours=24):
    """
    从rss_items中获取过去24小时新闻。
    优先使用 published，无法解析时使用 collected_at。
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = cur.execute("""
        SELECT
            id,
            guid,
            published,
            source,
            title,
            url,
            summary,
            content,
            collected_at
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
    """兼容RSS常见时间格式"""
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
# 2. DeepSeek 调用
# ============================================================

def get_deepseek_client():
    from openai import OpenAI

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")

    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )


def call_deepseek(prompt):
    """使用 requests 调用 DeepSeek API（无需 openai 库）"""
    import requests

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")

    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    r = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        },
        timeout=120
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ============================================================
# 3. JSON解析
# ============================================================

def extract_json(text):
    if not text:
        return None

    text = text.strip()

    # 去掉markdown代码块
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            lines = lines[1:]
            if lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

    # 直接解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 从第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return None


# ============================================================
# 4. 批量提示词（ONE BIG EVENT）
# ============================================================

def make_batch_prompt(items, current_time, market_text):
    news_blocks = []

    for i, item in enumerate(items):
        news_blocks.append(
            f"""
================ NEWS {i} ================

NEWS_ID:
{item.get("id", "")}

SOURCE:
{item.get("source", "")}

PUBLISHED:
{item.get("published", "")}

TITLE:
{item.get("title", "")}

SUMMARY:
{item.get("summary", "")}

CONTENT:
{item.get("content", "")[:3000]}

URL:
{item.get("url", "")}

===========================================
"""
        )

    news_text = "\n".join(news_blocks)

    return f"""
def make_batch_prompt(items, current_time, market_text):
    # ... 前面的 news_blocks 构建保持不变 ...

    return f"""
你是一名全球宏观、科技产业、政策和事件驱动投资领域的资深策略分析师。

当前时间：{current_time}

============================================================
你的核心任务
============================================================

从过去24小时新闻中，识别出：

**所有具有潜在预期差的事件**

不限制数量，但最多输出10个。

============================================================
筛选标准（按重要性排序）
============================================================

1. **预期差**：市场定价 vs 事件实际含义的差距（最重要）
2. **边际变化**：相比昨天，今天发生了什么新的事实
3. **产业链传导**：能否影响至少2层产业链
4. **A股映射**：是否能够映射到明确的A股标的

============================================================
重点关注“异常”信号
============================================================

以下情况应给予更高权重：

1. **价格异常**：
   - 某股票突然大涨/大跌，但没有对应的重大新闻
   - 某板块集体异动，但市场解读不充分

2. **基本面异常**：
   - 冷门行业公司突然获得大订单
   - 长期低迷的产业链出现反转信号
   - 小众技术突然获得巨头认可

3. **政策异常**：
   - 原本不可能的政策方向突然松动
   - 小范围试点突然扩大为全面政策

4. **人物言论异常**：
   - 一贯保守的官员/CEO突然释放激进信号
   - 同行中第一个改变观点的关键人物

5. **产业链异常**：
   - 上游产能突然收缩/扩张
   - 核心供应商的客户结构突然变化

============================================================
输出格式（最多10个事件）
============================================================

{{
    "signal": "MULTIPLE_CANDIDATES",
    "candidates": [
        {{
            "title": "",
            "category": "",
            "news_summary": "",
            "what_changed": "",
            "expectation_gap": "high|medium|low",
            "expectation_gap_detail": "",
            "abnormality_score": 0-100,
            "abnormality_reason": "",
            "a_share_idea": {{
                "name": "",
                "ticker": "",
                "type": "stock|ETF",
                "logic": "",
                "directness": "DIRECT|INDIRECT|SECOND_ORDER"
            }},
            "us_reference": [],
            "industry_chain_logic": "",
            "investment_thesis": "",
            "key_risks": [],
            "catalyst_timeline": ""
        }}
    ]
}}

如果没有任何事件有预期差：
{{"signal": "NO_CLEAR_EDGE"}}

============================================================
硬性要求
============================================================

1. 最多输出10个事件，按预期差从高到低排序
2. 只包含有明确A股映射的事件
3. 如果某事件已经被市场充分定价，排除
4. 不要只输出“最大”的新闻，要输出“最异常”的新闻
5. 只返回JSON

============================================================
过去24小时新闻
============================================================

{news_text}
"""


# ============================================================
# 5. A股映射检查
# ============================================================

def get_a_share_idea(result):
    if not isinstance(result, dict):
        return None

    event = result.get("event")
    if not isinstance(event, dict):
        return None

    idea = event.get("a_share_idea")
    if not isinstance(idea, dict):
        return None

    return idea


def has_valid_a_share_mapping(result):
    idea = get_a_share_idea(result)
    if not idea:
        return False

    name = str(idea.get("name", "")).strip()
    ticker = str(idea.get("ticker", "")).strip()
    logic = str(idea.get("logic", "")).strip()

    if not name or not ticker or not logic:
        return False

    invalid = {"unknown", "null", "none", "n/a", "暂无", "不确定"}
    if name.lower() in invalid or ticker.lower() in invalid:
        return False

    return True


# ============================================================
# 6. A股映射二次补全
# ============================================================

def make_mapping_repair_prompt(result, market_text):
    event = result.get("event", {})

    return f"""
你是一名A股产业链首席研究员。

现在已经确定了下面这个全球重大事件。

不要重新选择事件。

你的唯一任务：

寻找一个与事件基本面联系最直接的：

A股上市公司

或者

A股ETF。

============================================================
事件
============================================================

{json.dumps(event, ensure_ascii=False, indent=2)}

============================================================
最新市场行情
============================================================

{market_text}

============================================================
要求
============================================================

必须判断：

1. 事件是否真正影响这个公司/ETF；

2. 影响的是：

收入
订单
成本
利润
资本开支
估值

中的哪一个；

3. 产业链传导路径；

4. 当前股票是否已经price in；

5. 未来1～4周是否还有上涨空间。

优先：

直接受益

其次：

间接受益

最后：

二阶受益

禁止纯概念。

如果没有可靠A股映射：

返回null。

============================================================
输出
============================================================

{{
    "a_share_idea": {{

        "name": "",
        "ticker": "",
        "type": "stock|ETF",

        "logic": "",

        "directness": "DIRECT|INDIRECT|SECOND_ORDER",

        "current_price_reaction": "",

        "valuation_room": ""

    }}
}}

或者：

{{
    "a_share_idea": null
}}

只返回JSON。
"""


def repair_a_share_mapping(result, market_text):
    print("[BATCH] 启动A股映射二次分析...")

    try:
        prompt = make_mapping_repair_prompt(result, market_text)
        raw = call_deepseek(prompt)
        repaired = extract_json(raw)

        if not repaired:
            print("[BATCH] A股映射二次分析JSON解析失败")
            return result

        mapping = repaired.get("a_share_idea")
        if not isinstance(mapping, dict):
            print("[BATCH] 二次分析没有找到A股映射")
            return result

        event = result.get("event")
        if not isinstance(event, dict):
            return result

        event["a_share_idea"] = mapping
        print(f"[BATCH] A股映射补全：{mapping.get('name', '')} {mapping.get('ticker', '')}")

        return result

    except Exception as e:
        print(f"[BATCH] A股映射二次分析失败：{e}")
        return result


# ============================================================
# 7. 保存ONE BIG EVENT（修正版）
# ============================================================

def save_one_big_event(result):
    """
    把新版ONE BIG EVENT转换成现有event_scores表结构。
    使用 insert_score 代替不存在的 insert_batch_events。
    """
    event = result.get("event", {})
    scores = result.get("scores", {})
    idea = event.get("a_share_idea", {})

    # 获取源新闻ID
    source_ids = event.get("source_news_ids", [])
    rss_item_id = None
    if source_ids:
        try:
            rss_item_id = int(source_ids[0])
        except Exception:
            pass

    if rss_item_id is None:
        print("[BATCH] 没有有效source_news_id，跳过数据库保存")
        return

    # 构建评分数据（使用现有字段）
    score_data = {
        "category": event.get("category", "other"),
        "event_type": event.get("event_cluster", ""),
        "novelty": scores.get("novelty", 0),
        "economic_impact": scores.get("fundamental_impact", 0),
        "transmission": scores.get("transmission", 0),
        "expectation_gap": scores.get("expectation_gap", 50),
        "market_sensitivity": scores.get("market_mispricing", 0),
        "event_score": scores.get("investment_score", 0),
        "direction": event.get("direction", "unknown"),  # 从事件中读取方向
        "affected_assets": json.dumps({
            "a_share": idea,
            "us_reference": event.get("us_reference", []),
            "expectation_gap_detail": event.get("expectation_gap_detail", ""),
            "market_price_reaction": event.get("market_price_reaction", ""),
            "market_mispricing": event.get("market_mispricing", ""),
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

    # 调用已有的 insert_score
    insert_score(rss_item_id, score_data)
    print(f"[BATCH] ONE BIG EVENT 已保存数据库，A股：{idea.get('name', '')} ({idea.get('ticker', '')})")


# ============================================================
# 8. 主函数：run_batch
# ============================================================
def run_batch(market_text="unknown"):
    # ... 前面的代码保持不变 ...

    result = extract_json(raw)

    if result.get("signal") == "NO_CLEAR_EDGE":
        print("[BATCH] 今天没有足够大的预期差")
        return None

    if result.get("signal") != "MULTIPLE_CANDIDATES":
        print("[BATCH] LLM返回格式异常")
        return None

    candidates = result.get("candidates", [])
    print(f"[BATCH] LLM返回 {len(candidates)} 个候选事件")

    # 按异常程度排序
    candidates.sort(key=lambda x: x.get("abnormality_score", 0), reverse=True)

    for idx, event in enumerate(candidates):
        # 每个事件单独保存到数据库
        # 使用相同的 save_one_big_event 但传入单个事件
        score = event.get("scores", {}).get("investment_score", 0)
        print(f"[BATCH] {idx+1}. {event['title'][:50]}... (评分: {score})")

        # 保存每个事件
        save_single_event(event)

    return result

