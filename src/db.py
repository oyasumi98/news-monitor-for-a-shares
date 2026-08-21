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
你是一名全球宏观、科技产业、政策和事件驱动投资领域的资深策略分析师。

当前时间：

{current_time}

============================================================
你的唯一任务
============================================================

从过去24小时新闻中：

只寻找一个：

ONE BIG EVENT

也就是：

未来1～4周最可能产生明显资产价格变化，
并且目前仍然存在明显预期差的一个事件。

不是选择最热门新闻。

不是选择新闻影响最大新闻。

而是寻找：

“市场还没有充分定价的重大边际变化”。

============================================================
一、严格过去24小时
============================================================

只能使用过去24小时发生的事件。

超过24小时：

不得作为核心事件。

旧新闻今天再次报道：

不得视为新事件。

============================================================
二、严格事件去重
============================================================

不同媒体报道同一事件：

必须合并。

例如：

美国30年期美债收益率上升

美国财政赤字担忧

全球长期融资成本上升

如果本质由同一个核心驱动因素导致：

必须视为一个EVENT CLUSTER。

不能分别输出。

============================================================
三、最重要：寻找边际变化
============================================================

重点寻找：

新数据
新订单
新产品
新技术
新实验结果
新产能
新资本开支
新融资
新政策
新监管
重要人物最新表态
产业链供需变化

必须回答：

市场原来知道什么？

过去24小时新增了什么？

这个新增信息为什么可能改变未来盈利或者估值？

============================================================
四、特别关注科技产业链
============================================================

重点寻找：

AI
半导体
先进封装
HBM
光模块
服务器
数据中心
电力
机器人
自动驾驶
云计算
软件
新能源
生物科技

但不限于上述行业。

必须至少推演：

事件
→
产业链
→
具体公司
→
盈利

至少两层。

============================================================
五、必须结合最新市场行情
============================================================

以下是最新市场数据：

{market_text}

必须考虑：

1. 最新股票涨跌幅；
2. 最近几日表现；
3. 是否已经明显上涨；
4. 是否已经充分price in；
5. 新闻和股价是否存在背离。

最值得关注的是：

“基本面发生重大变化，
但股票还没有充分反映。”

============================================================
六、A股映射
============================================================

最终必须找到：

一个明确A股股票或者ETF。

优先级：

DIRECT
>
INDIRECT
>
SECOND_ORDER

禁止纯概念股。

必须说明：

事件
→
产业链变化
→
公司业务变化
→
收入/订单/成本/盈利
→
估值
→
股价

如果一个公司无法建立完整逻辑：

不要选择。

ETF也可以。

例如：

某个产业发生系统性变化，
但没有单一公司能够代表，
可以选择对应行业ETF。

============================================================
七、重要人物
============================================================

如果过去24小时存在重要人物讲话：

例如：

企业CEO
科技公司创始人
央行官员
财政官员
知名投资人
产业专家

如果其观点对：

基本面
产业链
资本开支
技术路线

有实质影响：

必须考虑。

但是：

普通评论不要纳入。

============================================================
八、未来1～4周
============================================================

必须推演：

BASE CASE

BULL CASE

BEAR CASE

以及未来可能验证逻辑的：

财报
订单
政策
产业数据
产品发布
产能
价格
资本开支
技术验证

============================================================
九、最终评分
============================================================

重点不是新闻本身重要程度。

而是：

“市场尚未定价程度”。

investment_score：

40% expectation_gap

20% fundamental_impact

15% transmission

15% market_mispricing

10% catalyst_strength

如果：

新闻很重要，
但是股票已经上涨30%：

降低评分。

如果：

新闻非常重要，
但对应A股还没有反应：

提高评分。

============================================================
十、只输出一个事件
============================================================

如果存在：

{{
    "signal": "ONE_BIG_EVENT",

    "event": {{

        "title": "",

        "category": "",

        "event_cluster": "",

        "published_time": "",

        "source_news_ids": [],

        "source_urls": [],

        "news_summary": "",

        "what_changed": "",

        "why_now": "",

        "market_consensus": "",

        "expectation_gap": "",

        "expectation_gap_detail": "",

        "market_price_reaction": "",

        "market_mispricing": "",

        "industry_chain_logic": "",

        "direction": "positive|negative|mixed",

        "a_share_idea": {{

            "name": "",
            "ticker": "",
            "type": "stock|ETF",

            "logic": "",

            "directness": "DIRECT|INDIRECT|SECOND_ORDER",

            "current_price_reaction": "",

            "valuation_room": ""

        }},

        "us_reference": [],

        "speaker": {{

            "name": null,
            "role": null,
            "statement_type": null,
            "core_view": null

        }},

        "investment_thesis": "",

        "earnings_impact": "",

        "valuation_impact": "",

        "future_1_4_weeks": {{

            "base_case": "",
            "bull_case": "",
            "bear_case": ""

        }},

        "key_catalysts": [],

        "key_risks": [],

        "what_to_watch_next": [],

        "final_conclusion": ""

    }},

    "scores": {{

        "novelty": 0,
        "fundamental_impact": 0,
        "transmission": 0,
        "expectation_gap": 0,
        "market_mispricing": 0,
        "catalyst_strength": 0,
        "investment_score": 0

    }}

}}

如果没有真正的预期差：

{{
    "signal": "NO_CLEAR_EDGE"
}}

============================================================
硬性要求
============================================================

1. 只允许一个事件。
2. 不允许TOP5。
3. 不允许多个候选。
4. 必须有明确A股股票或ETF。
5. 必须有基本面逻辑。
6. 必须结合最新股价。
7. 不允许使用超过24小时的旧新闻。
8. 同一事件必须去重。
9. 不允许为了凑股票而强行关联。
10. 如果新闻非常重要，但没有A股映射，返回NO_CLEAR_EDGE。
11. 不要编造股票代码。
12. 不要编造产业链关系。
13. 只返回JSON。

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
    print("[BATCH] ===== GLOBAL MARKET SURPRISE DETECTOR =====")

    init_db()

    now = datetime.now(timezone.utc)
    print(f"[BATCH] 当前UTC时间：{now.isoformat()}")
    print("[BATCH] 时间窗口：过去24小时")

    items = get_recent_news(hours=24)
    print(f"[BATCH] 获取新闻：{len(items)}条")

    if not items:
        print("[BATCH] 过去24小时没有新闻")
        return None

    if market_text != "unknown":
        print("[BATCH] 使用最新市场数据")
    else:
        print("[BATCH] 市场数据不可用")

    prompt = make_batch_prompt(items, now.isoformat(), market_text)
    print(f"[BATCH] Prompt长度：{len(prompt)}字符")

    print("[BATCH] 使用DeepSeek...")
    try:
        raw = call_deepseek(prompt)
    except Exception as e:
        print(f"[BATCH] DeepSeek调用失败：{e}")
        return None

    print(f"[BATCH] LLM返回长度：{len(raw)}字符")

    result = extract_json(raw)
    if not result:
        print("[BATCH] LLM JSON解析失败")
        print(raw[:1000])
        return None

    if result.get("signal") == "NO_CLEAR_EDGE":
        print("[BATCH] 今天没有足够大的预期差")
        return None

    if result.get("signal") != "ONE_BIG_EVENT":
        print("[BATCH] LLM没有返回ONE_BIG_EVENT")
        return None

    event = result.get("event")
    if not isinstance(event, dict):
        print("[BATCH] event字段无效")
        return None

    print("[BATCH] LLM返回候选事件：1个")
    print(f"[BATCH] 事件：{event.get('title', '')}")

    # 检查A股映射
    if not has_valid_a_share_mapping(result):
        print("[BATCH] 第一次分析没有明确A股/ETF映射")
        result = repair_a_share_mapping(result, market_text)

    if not has_valid_a_share_mapping(result):
        print("[BATCH] 淘汰：没有可靠A股/ETF映射")
        print("[BATCH] 没有事件通过最终筛选")
        return None

    event = result["event"]
    idea = event["a_share_idea"]
    scores = result.get("scores", {})

    print("[BATCH] ========================================")
    print("[BATCH] FINAL ONE BIG EVENT")
    print(f"[BATCH] 标题：{event.get('title', '')}")
    print(f"[BATCH] A股：{idea.get('name', '')} {idea.get('ticker', '')}")
    print(f"[BATCH] 投资逻辑：{idea.get('logic', '')}")
    print(f"[BATCH] Investment Score：{scores.get('investment_score', 0)}")
    print("[BATCH] ========================================")

    # 保存数据库
    try:
        save_one_big_event(result)
    except Exception as e:
        print(f"[BATCH] 保存数据库失败：{e}")

    return result
