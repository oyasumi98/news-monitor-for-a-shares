import sqlite3
import json
import requests
from datetime import datetime, timedelta, timezone

from . import config
from .db import init_db
from .llm_prompt import make_batch_prompt


# ============================================================
# 基础工具
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def normalize_time(value):
    """
    将数据库中的时间尽可能转换成 timezone-aware datetime。
    """
    if not value:
        return None

    try:
        value = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


# ============================================================
# 获取过去24小时新闻
# ============================================================

def get_unscored_news(limit=None):
    """
    获取过去24小时新闻。

    注意：
    不再使用“是否已经存在event_scores”作为唯一过滤条件。

    原因：
    某一条新闻过去已经被评分，不代表它今天不能参与
    ONE BIG EVENT重新竞争。

    真正的时间窗口由 collected_at / published 控制。
    """

    if limit is None:
        limit = config.BATCH_LIMIT

    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row

    # UTC时间
    threshold = utc_now() - timedelta(hours=24)

    # ISO格式
    threshold_iso = threshold.isoformat()

    rows = con.execute(
        """
        SELECT r.*
        FROM rss_items r
        WHERE r.collected_at >= ?
        ORDER BY r.collected_at DESC
        LIMIT ?
        """,
        (threshold_iso, limit)
    ).fetchall()

    con.close()

    items = [dict(row) for row in rows]

    # ========================================================
    # 程序层再次进行24小时过滤
    # ========================================================

    valid_items = []

    now = utc_now()

    for item in items:

        dt = normalize_time(
            item.get("published")
            or item.get("published_at")
            or item.get("collected_at")
        )

        if dt is None:
            # 时间无法判断，保留，但标记
            item["_time_unknown"] = True
            valid_items.append(item)
            continue

        age_hours = (now - dt).total_seconds() / 3600

        if age_hours <= 24:
            item["_time_unknown"] = False
            item["_age_hours"] = round(age_hours, 2)
            valid_items.append(item)

    return valid_items


# ============================================================
# DeepSeek
# ============================================================

def call_deepseek_batch(prompt):

    """
    DeepSeek调用。
    """

    r = requests.post(
        f"{config.DEEPSEEK_BASE_URL}/chat/completions",

        headers={
            "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        },

        json={
            "model": config.DEEPSEEK_MODEL,

            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            "temperature": 0.1,

            "response_format": {
                "type": "json_object"
            }
        },

        timeout=180
    )

    r.raise_for_status()

    return r.json()["choices"][0]["message"]["content"]


# ============================================================
# Gemini
# ============================================================

def call_gemini_batch(prompt):

    """
    Gemini调用。
    """

    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent",

        params={
            "key": config.GEMINI_API_KEY
        },

        json={
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],

            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        },

        timeout=180
    )

    r.raise_for_status()

    return (
        r.json()
        ["candidates"][0]
        ["content"]["parts"][0]["text"]
    )


# ============================================================
# 默认字段
# ============================================================

def fill_defaults(event):

    """
    防止LLM漏字段导致数据库写入失败。
    """

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

        "price_anomaly": {
            "stock": "",
            "change_pct": 0,
            "volume": "",
            "suspected_reason": "",
            "confidence": None
        },

        "speaker": {
            "name": None,
            "role": None,
            "statement_type": None,
            "core_view": None
        },

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

        "confidence": 0,

        "affected_assets": "",

        "affected_industries": "",

        # ====================================================
        # 新增字段
        # ====================================================

        "market_mispricing": 0,

        "catalyst_strength": 0,

        "valuation_room": 0,

        "investment_score": 0,

        "why_this_event": "",

        "market_consensus": "",

        "why_market_may_be_wrong": "",

        "why_now": "",

        "investment_thesis": "",

        "earnings_impact": "",

        "valuation_impact": "",

        "market_logic": "",

        "future_1_4_weeks": {},

        "key_catalysts": [],

        "key_risks": [],

        "what_to_watch_next": [],

        "final_conclusion": "",

        "a_share_idea": {}
    }

    for key, default in defaults.items():

        if key not in event or event[key] is None:
            event[key] = default

    return event


# ============================================================
# 数字安全转换
# ============================================================

def safe_float(value, default=0):

    try:
        if value is None:
            return default

        if isinstance(value, str):

            value = (
                value
                .replace("%", "")
                .replace(",", "")
                .strip()
            )

        return float(value)

    except Exception:

        return default


# ============================================================
# 计算最终投资评分
# ============================================================

def calculate_investment_score(event):

    """
    防止LLM出现：

    Novelty 1
    Impact 1
    Transmission 1

    这种异常结果。

    如果LLM已经给出investment_score：
    优先使用。

    否则根据核心维度重新计算。
    """

    novelty = safe_float(
        event.get("novelty"),
        0
    )

    expectation_gap = safe_float(
        event.get("expectation_gap_score"),
        0
    )

    market_mispricing = safe_float(
        event.get("market_mispricing"),
        0
    )

    economic_impact = safe_float(
        event.get("economic_impact"),
        0
    )

    transmission = safe_float(
        event.get("transmission"),
        0
    )

    market_sensitivity = safe_float(
        event.get("market_sensitivity"),
        0
    )

    catalyst_strength = safe_float(
        event.get("catalyst_strength"),
        0
    )

    valuation_room = safe_float(
        event.get("valuation_room"),
        0
    )

    # ========================================================
    # 新评分模型
    # ========================================================

    score = (

        0.20 * novelty

        + 0.25 * expectation_gap

        + 0.20 * market_mispricing

        + 0.10 * economic_impact

        + 0.10 * transmission

        + 0.05 * market_sensitivity

        + 0.05 * catalyst_strength

        + 0.05 * valuation_room

    )

    return round(score, 2)


# ============================================================
# 最终候选事件过滤
# ============================================================

def validate_event(event):

    """
    对LLM结果做程序层硬过滤。
    """

    # --------------------------------------------------------
    # 1. 时间窗口
    # --------------------------------------------------------

    if event.get("is_valid_time_window") is False:

        print("[BATCH] 淘汰：超过24小时")

        return False

    # --------------------------------------------------------
    # 2. 重复事件
    # --------------------------------------------------------

    if event.get("is_repeat") is True:

        print("[BATCH] 淘汰：重复事件")

        return False

    # --------------------------------------------------------
    # 3. 是否存在A股映射
    # --------------------------------------------------------

    a_stocks = event.get(
        "strong_linked_a_stocks",
        []
    )

    a_idea = event.get(
        "a_share_idea",
        {}
    )

    ticker = ""

    if isinstance(a_idea, dict):

        ticker = (
            a_idea.get("ticker")
            or a_idea.get("name")
            or ""
        )

    if not a_stocks and not ticker:

        print(
            "[BATCH] 淘汰：没有明确A股/ETF映射"
        )

        return False

    # --------------------------------------------------------
    # 4. 必须有边际变化
    # --------------------------------------------------------

    marginal_change = (
        event.get("marginal_change")
        or event.get("core_change")
        or ""
    )

    if len(str(marginal_change).strip()) < 5:

        print(
            "[BATCH] 淘汰：没有明确边际变化"
        )

        return False

    # --------------------------------------------------------
    # 5. 投资评分
    # --------------------------------------------------------

    score = calculate_investment_score(event)

    event["investment_score"] = score

    # --------------------------------------------------------
    # 6. 低分直接淘汰
    # --------------------------------------------------------

    if score < 60:

        print(
            f"[BATCH] 淘汰：投资评分过低 {score}"
        )

        return False

    return True


# ============================================================
# 找到事件对应的RSS新闻
# ============================================================

def _get_event_rss_item_id(event, all_items, cur):

    """
    找到事件对应的第一条原始新闻。

    source_news_ids优先。
    """

    source_ids = event.get(
        "source_news_ids",
        []
    )

    # --------------------------------------------------------
    # source_news_ids
    # --------------------------------------------------------

    if isinstance(source_ids, list):

        for source_id in source_ids:

            # 如果是新闻数组下标
            if isinstance(source_id, int):

                if 0 <= source_id < len(all_items):

                    item_id = all_items[source_id].get("id")

                    if item_id is not None:

                        return item_id

                # 如果是数据库ID
                cur.execute(
                    """
                    SELECT id
                    FROM rss_items
                    WHERE id = ?
                    """,
                    (source_id,)
                )

                row = cur.fetchone()

                if row:

                    return row[0]

    # --------------------------------------------------------
    # 尝试title匹配
    # --------------------------------------------------------

    title = (
        event.get("event_title")
        or event.get("title")
        or ""
    )

    if title:

        words = title[:40].strip()

        if len(words) >= 5:

            cur.execute(
                """
                SELECT id
                FROM rss_items
                WHERE title LIKE ?
                ORDER BY collected_at DESC
                LIMIT 1
                """,
                (f"%{words}%",)
            )

            row = cur.fetchone()

            if row:

                return row[0]

    # --------------------------------------------------------
    # news_summary匹配
    # --------------------------------------------------------

    summary = event.get(
        "news_summary",
        ""
    )

    if summary:

        keyword = summary[:30].strip()

        if len(keyword) >= 5:

            cur.execute(
                """
                SELECT id
                FROM rss_items
                WHERE title LIKE ?
                ORDER BY collected_at DESC
                LIMIT 1
                """,
                (f"%{keyword}%",)
            )

            row = cur.fetchone()

            if row:

                return row[0]

    # --------------------------------------------------------
    # event_cluster匹配
    # --------------------------------------------------------

    cluster = event.get(
        "event_cluster",
        ""
    )

    if cluster:

        keyword = cluster[:20].strip()

        if len(keyword) >= 5:

            cur.execute(
                """
                SELECT id
                FROM rss_items
                WHERE title LIKE ?
                ORDER BY collected_at DESC
                LIMIT 1
                """,
                (f"%{keyword}%",)
            )

            row = cur.fetchone()

            if row:

                return row[0]

    return None


# ============================================================
# 保存ONE BIG EVENT
# ============================================================

def insert_batch_event(event, all_items):

    """
    只保存最终胜出的ONE BIG EVENT。
    """

    event = fill_defaults(event)

    con = sqlite3.connect(
        config.DB_PATH
    )

    cur = con.cursor()

    rss_item_id = _get_event_rss_item_id(
        event,
        all_items,
        cur
    )

    if rss_item_id is None:

        con.close()

        print(
            "[BATCH] 无法找到对应RSS新闻ID"
        )

        return False

    # ========================================================
    # 最终评分
    # ========================================================

    event["investment_score"] = calculate_investment_score(
        event
    )

    # ========================================================
    # 构建数据库数据
    # ========================================================

    score_data = {

        "rss_item_id":
            rss_item_id,

        "category":
            event.get(
                "category",
                "other"
            ),

        "event_type":
            (
                event.get("event_cluster")
                or event.get("event_type")
                or ""
            )[:100],

        "novelty":
            safe_float(
                event.get("novelty")
            ),

        "economic_impact":
            safe_float(
                event.get("economic_impact")
            ),

        "transmission":
            safe_float(
                event.get("transmission")
            ),

        "expectation_gap":
            safe_float(
                event.get(
                    "expectation_gap_score"
                )
            ),

        "market_sensitivity":
            safe_float(
                event.get(
                    "market_sensitivity"
                )
            ),

        # 这里把最终投资评分写入event_score
        "event_score":
            safe_float(
                event.get(
                    "investment_score"
                )
            ),

        "direction":
            event.get(
                "direction",
                "unknown"
            ),

        "affected_assets":
            event.get(
                "affected_assets",
                ""
            ),

        "affected_industries":
            event.get(
                "affected_industries",
                ""
            ),

        "rationale":
            (
                event.get("final_conclusion")
                or event.get("rationale")
                or ""
            ),

        "second_order_effects":
            event.get(
                "second_order_effects",
                ""
            ),

        "risks":
            event.get(
                "risks",
                ""
            ),

        "model":
            "one-big-event",

        "scored_at":
            utc_now().isoformat(),

        "source_news_ids":
            json.dumps(
                event.get(
                    "source_news_ids",
                    []
                ),
                ensure_ascii=False
            ),

        "strong_linked_us_stocks":
            json.dumps(
                event.get(
                    "strong_linked_us_stocks",
                    []
                ),
                ensure_ascii=False
            ),

        "strong_linked_a_stocks":
            json.dumps(
                event.get(
                    "strong_linked_a_stocks",
                    []
                ),
                ensure_ascii=False
            ),

        "market_crowdedness":
            event.get(
                "market_crowdedness",
                "unknown"
            ),

        "expectation_gap_detail":
            event.get(
                "expectation_gap_detail",
                ""
            ),

        "price_anomaly":
            json.dumps(
                event.get(
                    "price_anomaly",
                    {}
                ),
                ensure_ascii=False
            ),

        "validation_catalyst":
            event.get(
                "validation_catalyst",
                ""
            ),

        "confidence":
            safe_float(
                event.get(
                    "confidence",
                    0
                )
            ),

        "news_summary":
            event.get(
                "news_summary",
                ""
            ),

        "marginal_change":
            event.get(
                "marginal_change",
                ""
            ),

        "industry_chain_logic":
            event.get(
                "industry_chain_logic",
                ""
            )
    }

    # ========================================================
    # 读取数据库真实字段
    # ========================================================

    columns = _get_table_columns(cur)

    insert_data = {
        k: v
        for k, v in score_data.items()
        if k in columns
    }

    # ========================================================
    # 防止重复保存
    # ========================================================

    cur.execute(
        """
        SELECT id
        FROM event_scores
        WHERE rss_item_id = ?
        """,
        (rss_item_id,)
    )

    existing = cur.fetchone()

    if existing:

        # ----------------------------------------------------
        # 更新
        # ----------------------------------------------------

        assignments = []

        for key in insert_data:

            if key == "rss_item_id":
                continue

            assignments.append(
                f"{key} = :{key}"
            )

        sql = f"""
            UPDATE event_scores
            SET {", ".join(assignments)}
            WHERE rss_item_id = :rss_item_id
        """

        cur.execute(
            sql,
            insert_data
        )

    else:

        # ----------------------------------------------------
        # 插入
        # ----------------------------------------------------

        columns_str = ", ".join(
            insert_data.keys()
        )

        placeholders = ", ".join(
            f":{k}"
            for k in insert_data.keys()
        )

        sql = f"""
            INSERT INTO event_scores
            ({columns_str})
            VALUES
            ({placeholders})
        """

        cur.execute(
            sql,
            insert_data
        )

    con.commit()

    con.close()

    return True


# ============================================================
# 数据库字段
# ============================================================

def _get_table_columns(cur):

    cur.execute(
        "PRAGMA table_info(event_scores)"
    )

    return [
        row[1]
        for row in cur.fetchall()
    ]


# ============================================================
# JSON解析
# ============================================================

def parse_llm_json(raw):

    """
    兼容：

    {
        "signal": "ONE_BIG_EVENT",
        ...
    }

    或：

    {
        "events": [...]
    }

    或旧版本：

    [...]
    """

    raw = (
        raw
        .strip()
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    data = json.loads(raw)

    # --------------------------------------------------------
    # 新版ONE BIG EVENT
    # --------------------------------------------------------

    if isinstance(data, dict):

        signal = data.get(
            "signal"
        )

        if signal == "NO_CLEAR_EDGE":

            return []

        if signal == "ONE_BIG_EVENT":

            return [data]

        # ----------------------------------------------------
        # events数组
        # ----------------------------------------------------

        if isinstance(
            data.get("events"),
            list
        ):

            return data["events"]

        # ----------------------------------------------------
        # event对象
        # ----------------------------------------------------

        if isinstance(
            data.get("event"),
            dict
        ):

            event = data["event"]

            # 将外层信息合并进去
            for key, value in data.items():

                if key not in (
                    "event",
                    "signal"
                ):

                    event.setdefault(
                        key,
                        value
                    )

            return [event]

        # ----------------------------------------------------
        # 默认把整个dict作为事件
        # ----------------------------------------------------

        return [data]

    # --------------------------------------------------------
    # 旧版list
    # --------------------------------------------------------

    if isinstance(data, list):

        return data

    return []


# ============================================================
# 从多个候选中选出唯一事件
# ============================================================

def select_one_big_event(events):

    """
    最终保险机制：

    无论LLM返回多少个事件，
    最终只能保存一个。

    优先：
    investment_score

    其次：
    event_score
    """

    valid_events = []

    for event in events:

        if not isinstance(
            event,
            dict
        ):
            continue

        event = fill_defaults(event)

        # ----------------------------------------------------
        # 新评分
        # ----------------------------------------------------

        event["investment_score"] = (
            calculate_investment_score(
                event
            )
        )

        # ----------------------------------------------------
        # 硬过滤
        # ----------------------------------------------------

        if not validate_event(event):

            continue

        valid_events.append(event)

    if not valid_events:

        return None

    # --------------------------------------------------------
    # 排序
    # --------------------------------------------------------

    valid_events.sort(
        key=lambda x: (
            safe_float(
                x.get(
                    "investment_score",
                    0
                )
            ),
            safe_float(
                x.get(
                    "expectation_gap_score",
                    0
                )
            ),
            safe_float(
                x.get(
                    "novelty",
                    0
                )
            )
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # 只允许一个
    # --------------------------------------------------------

    winner = valid_events[0]

    winner["is_final_winner"] = True

    winner["final_rank"] = 1

    # 保存内部候选数量，方便调试
    winner["_candidate_count"] = len(
        valid_events
    )

    return winner


# ============================================================
# 主流程
# ============================================================

def run_batch(
    market_text=None,
    limit=None,
    hours=24,
    max_events=1
):

    """
    GLOBAL MARKET SURPRISE DETECTOR

    核心流程：

    过去24小时新闻
        ↓
    LLM语义去重
        ↓
    事件聚类
        ↓
    预期差分析
        ↓
    A股映射
        ↓
    最终PK
        ↓
    ONE BIG EVENT

    参数：

    market_text:
        最新市场行情

    limit:
        RSS最多读取多少条

    hours:
        时间窗口，默认24小时

    max_events:
        最终事件数量，强制为1
    """

    print(
        "\n[BATCH] "
        "===== GLOBAL MARKET SURPRISE DETECTOR ====="
    )

    # ========================================================
    # 初始化
    # ========================================================

    init_db()

    if limit is None:

        limit = config.BATCH_LIMIT

    # ========================================================
    # 获取新闻
    # ========================================================

    print(
        f"[BATCH] 时间窗口：过去{hours}小时"
    )

    items = get_unscored_news(
        limit
    )

    if not items:

        print(
            "[BATCH] 没有过去24小时新闻"
        )

        return None

    print(
        f"[BATCH] 获取新闻：{len(items)}条"
    )

    # ========================================================
    # 市场数据
    # ========================================================

    if market_text is None:

        print(
            "[BATCH] 未传入市场数据，尝试获取..."
        )

        try:

            from .market_data import (
                fetch_all_market_data,
                format_market_data_for_prompt
            )

            market_data = (
                fetch_all_market_data()
            )

            market_text = (
                format_market_data_for_prompt(
                    market_data
                )
            )

        except Exception as e:

            print(
                f"[BATCH] 市场数据获取失败：{e}"
            )

            market_text = "UNKNOWN"

    else:

        print(
            "[BATCH] 使用最新市场数据"
        )

    # ========================================================
    # 当前时间
    # ========================================================

    current_time = (
        utc_now().isoformat()
    )

    # ========================================================
    # 构建Prompt
    # ========================================================

    prompt = make_batch_prompt(
        items,
        current_time,
        market_text
    )

    print(
        "[BATCH] Prompt长度："
        f"{len(prompt)}字符"
    )

    # ========================================================
    # LLM
    # ========================================================

    raw = None

    try:

        if config.DEEPSEEK_API_KEY:

            print(
                "[BATCH] 使用DeepSeek..."
            )

            raw = call_deepseek_batch(
                prompt
            )

            model = "deepseek-one-big-event"

        elif config.GEMINI_API_KEY:

            print(
                "[BATCH] 使用Gemini..."
            )

            raw = call_gemini_batch(
                prompt
            )

            model = "gemini-one-big-event"

        else:

            raise RuntimeError(
                "未配置DeepSeek或Gemini API Key"
            )

    except Exception as e:

        print(
            f"[BATCH] LLM调用失败：{e}"
        )

        return None

    # ========================================================
    # 解析
    # ========================================================

    print(
        f"[BATCH] LLM返回长度：{len(raw)}字符"
    )

    try:

        events = parse_llm_json(
            raw
        )

    except Exception as e:

        print(
            f"[BATCH] JSON解析失败：{e}"
        )

        print(
            "[BATCH] 原始返回："
            f"{raw[:1000]}"
        )

        return None

    if not events:

        print(
            "[BATCH] 没有ONE BIG EVENT"
        )

        return None

    print(
        f"[BATCH] LLM返回候选事件："
        f"{len(events)}个"
    )

    # ========================================================
    # 最终PK
    # ========================================================

    winner = select_one_big_event(
        events
    )

    if winner is None:

        print(
            "[BATCH] 没有事件通过最终筛选"
        )

        return None

    # ========================================================
    # 写入模型信息
    # ========================================================

    winner["model"] = model

    # ========================================================
    # 强制只保存一个
    # ========================================================

    success = insert_batch_event(
        winner,
        items
    )

    if not success:

        print(
            "[BATCH] ONE BIG EVENT保存失败"
        )

        return None

    # ========================================================
    # 输出结果
    # ========================================================

    score = safe_float(
        winner.get(
            "investment_score"
        )
    )

    title = (
        winner.get("event", {})
        .get("title")
        if isinstance(
            winner.get("event"),
            dict
        )
        else None
    )

    if not title:

        title = (
            winner.get("event_title")
            or winner.get("news_summary")
            or winner.get("event_cluster")
            or "UNKNOWN"
        )

    a_idea = winner.get(
        "a_share_idea",
        {}
    )

    if isinstance(
        a_idea,
        dict
    ):

        a_name = (
            a_idea.get("name")
            or a_idea.get("ticker")
            or "UNKNOWN"
        )

    else:

        a_name = "UNKNOWN"

    print("\n")
    print("=" * 70)
    print("🎯 ONE BIG EVENT")
    print("=" * 70)

    print(
        f"事件：{title}"
    )

    print(
        f"投资评分：{score:.1f}"
    )

    print(
        f"A股映射：{a_name}"
    )

    print(
        f"预期差："
        f"{winner.get('expectation_gap', 'unknown')}"
    )

    print(
        f"拥挤度："
        f"{winner.get('market_crowdedness', 'unknown')}"
    )

    print(
        f"结论："
        f"{winner.get('final_conclusion', '')[:300]}"
    )

    print("=" * 70)

    return winner


# ============================================================
# 独立运行
# ============================================================

if __name__ == "__main__":

    run_batch(
        hours=24,
        max_events=1
    )
