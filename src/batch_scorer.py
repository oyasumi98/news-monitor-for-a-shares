# src/batch_scorer.py

import json
import os
from datetime import datetime, timedelta, timezone

from .db import get_recent_news


# ============================================================
# DeepSeek
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
    client = get_deepseek_client()

    response = client.chat.completions.create(
        model=os.getenv(
            "DEEPSEEK_MODEL",
            "deepseek-chat"
        ),
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1,
        max_tokens=8000
    )

    return response.choices[0].message.content


# ============================================================
# JSON解析
# ============================================================

def extract_json(text):
    """
    从LLM返回内容中提取JSON。
    """

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

    # 尝试寻找第一个 {
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
# Prompt
# ============================================================

def make_batch_prompt(items, current_time, market_text):

    news_blocks = []

    for i, item in enumerate(items):

        news_id = item.get("id", i)

        source = (
            item.get("source")
            or item.get("feed")
            or "unknown"
        )

        published = (
            item.get("published")
            or item.get("published_at")
            or item.get("collected_at")
            or "unknown"
        )

        title = item.get("title", "")

        summary = (
            item.get("summary")
            or item.get("description")
            or ""
        )

        url = (
            item.get("url")
            or item.get("link")
            or ""
        )

        news_blocks.append(
            f"""
================ NEWS {i} ================

NEWS_ID:
{news_id}

SOURCE:
{source}

PUBLISHED:
{published}

TITLE:
{title}

SUMMARY:
{summary}

URL:
{url}

===========================================
"""
        )

    news_text = "\n".join(news_blocks)

    return f"""
你是一名全球宏观、科技产业、政策和事件驱动投资领域的资深策略分析师。

当前时间：
{current_time}

============================================================
任务
============================================================

请从下面过去24小时新闻中，只寻找：

ONE BIG EVENT

即：

“未来1～4周最可能因为市场尚未充分定价，
而产生明显行情的一个重大事件。”

不是选择最热门新闻。

而是寻找：

预期差最大
+
基本面传导最清晰
+
A股映射最明确
+
当前股价尚未充分price in
+
未来存在验证催化剂

============================================================
第一步：严格限制过去24小时
============================================================

只分析过去24小时发生的新事件。

如果只是旧新闻再次报道：

淘汰。

如果多个媒体报道同一事件：

合并。

标题不同但本质相同：

必须视为同一个事件。

例如：

“美国30年美债收益率创新高”

“全球长期借贷成本上升”

“美国财政赤字担忧”

如果核心驱动因素相同：

必须聚类成一个事件。

============================================================
第二步：寻找边际变化
============================================================

必须回答：

市场昨天知道什么？

今天新增了什么？

重点寻找：

新数据
新订单
新产能
新政策
新技术
新融资
新资本开支
新产品
供应链变化
重要人物新表态

没有新边际变化：

淘汰。

============================================================
第三步：重点寻找预期差
============================================================

重点分析：

新闻发生后：

相关股票涨了多少？

市场已经price in多少？

是否存在：

基本面变化 > 股价变化

或者：

股价变化 > 基本面变化

尤其寻找：

新闻重大，但相关A股没有明显上涨。

这种情况可能存在最大的预期差。

============================================================
第四步：产业链分析
============================================================

尤其关注科技产业。

必须至少分析2～4层产业链。

例如：

AI资本开支
→ GPU
→ HBM
→ 先进封装
→ 光模块
→ PCB
→ 电力设备

不要只写：

“AI利好科技股”。

必须找到：

哪个具体环节的盈利预期可能发生变化。

============================================================
第五步：A股映射
============================================================

最终必须找到：

一个明确的A股上市公司或者A股ETF。

优先：

DIRECT
>
INDIRECT
>
SECOND_ORDER

禁止纯概念映射。

必须回答：

为什么这个事件会影响这个公司的：

收入
订单
成本
产能
盈利
估值

中的至少一项。

============================================================
第六步：最新行情
============================================================

必须使用下面的最新市场数据：

{market_text}

不要使用旧行情。

判断：

1. 股票是否已经大涨；
2. 是否已经连续上涨；
3. 是否明显拥挤；
4. 是否新闻很好但股价没有反应；
5. 是否股价已经提前交易。

============================================================
第七步：未来1～4周
============================================================

必须推演：

Base Case
Bull Case
Bear Case

并且给出未来可能验证逻辑的：

财报
订单
政策
产业数据
产品发布
产能
资本开支
价格
技术验证

============================================================
最终要求
============================================================

只允许输出一个事件。

如果没有真正明显的预期差：

返回：

{{
    "signal": "NO_CLEAR_EDGE"
}}

如果存在：

返回：

{{
    "signal": "ONE_BIG_EVENT",

    "event": {{
        "title": "",
        "category": "",
        "event_cluster": "",
        "published_time": "",

        "news_summary": "",
        "what_changed": "",
        "why_now": "",

        "market_consensus": "",
        "expectation_gap": "",
        "expectation_gap_detail": "",

        "market_mispricing": "",
        "market_price_reaction": "",

        "industry_chain_logic": "",

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
        "economic_impact": 0,
        "transmission": 0,
        "expectation_gap": 0,
        "market_mispricing": 0,
        "market_sensitivity": 0,
        "catalyst_strength": 0,
        "valuation_room": 0,
        "investment_score": 0
    }},

    "source_news_ids": []
}}

============================================================
硬性要求
============================================================

1. 只输出一个事件。
2. 不要输出TOP5。
3. 不要输出多个候选。
4. 必须有A股股票或ETF。
5. 股票必须有明确逻辑。
6. 不允许编造。
7. 不允许使用旧行情。
8. 不允许选择超过24小时的核心事件。
9. 不允许把同一事件拆成多个事件。
10. 不要因为新闻热门而提高评分。

只返回JSON。

============================================================
新闻
============================================================

{news_text}
"""


# ============================================================
# A股映射检查
# ============================================================

def get_a_share_idea(result):
    """
    新版JSON结构：

    result
        └── event
              └── a_share_idea
    """

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

    name = str(
        idea.get("name", "")
    ).strip()

    ticker = str(
        idea.get("ticker", "")
    ).strip()

    logic = str(
        idea.get("logic", "")
    ).strip()

    invalid = {
        "",
        "unknown",
        "null",
        "none",
        "n/a",
        "暂无",
        "不确定"
    }

    if name.lower() in invalid:
        return False

    if ticker.lower() in invalid:
        return False

    if not logic:
        return False

    return True


# ============================================================
# A股映射二次修复
# ============================================================

def make_mapping_repair_prompt(result, market_text):

    event = result.get(
        "event",
        {}
    )

    return f"""
你是一名A股产业链研究员。

现在已经确定了一个全球重大投资事件。

你不要重新选择事件。

你的唯一任务：

寻找一个与该事件基本面关系最直接的A股上市公司或A股ETF。

============================================================
事件
============================================================

{json.dumps(
    event,
    ensure_ascii=False,
    indent=2
)}

============================================================
最新市场数据
============================================================

{market_text}

============================================================
要求
============================================================

必须满足：

1. 必须是A股上市公司或者A股ETF。

2. 优先选择直接受益公司。

3. 不允许纯概念关联。

4. 必须解释：

事件
↓
产业链变化
↓
公司收入/订单/成本/盈利变化
↓
估值变化
↓
股价可能变化

5. 必须考虑当前股价。

6. 如果已经大涨，判断是否已经price in。

7. 如果存在更直接的A股标的，优先选择更直接的。

8. 如果不存在可靠映射，返回null。

============================================================
输出
============================================================

只返回：

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

不要输出任何其他内容。
"""


def repair_a_share_mapping(result, market_text):

    try:

        print("[BATCH] 未找到有效A股映射")
        print("[BATCH] 启动A股映射二次分析...")

        prompt = make_mapping_repair_prompt(
            result,
            market_text
        )

        response = call_deepseek(prompt)

        repaired = extract_json(response)

        if not repaired:
            print("[BATCH] A股映射二次分析JSON解析失败")
            return result

        mapping = repaired.get(
            "a_share_idea"
        )

        if not isinstance(mapping, dict):
            print("[BATCH] 二次分析未找到A股映射")
            return result

        event = result.get(
            "event"
        )

        if not isinstance(event, dict):
            return result

        event["a_share_idea"] = mapping

        print(
            "[BATCH] A股映射补全："
            f"{mapping.get('name', '')} "
            f"{mapping.get('ticker', '')}"
        )

        return result

    except Exception as e:

        print(
            f"[BATCH] A股映射二次分析失败：{e}"
        )

        return result


# ============================================================
# 主流程
# ============================================================

def run_batch(
    market_text="unknown",
    current_time=None
):

    print(
        "[BATCH] ===== GLOBAL MARKET SURPRISE DETECTOR ====="
    )

    # --------------------------------------------------------
    # 当前时间
    # --------------------------------------------------------

    if current_time is None:

        current_time = datetime.now(
            timezone.utc
        ).isoformat()

    print(
        f"[BATCH] 当前时间：{current_time}"
    )

    print(
        "[BATCH] 时间窗口：过去24小时"
    )

    # --------------------------------------------------------
    # 获取过去24小时新闻
    # --------------------------------------------------------

    try:

        items = get_recent_news(
            hours=24
        )

    except Exception as e:

        print(
            f"[BATCH] 获取新闻失败：{e}"
        )

        return

    if not items:

        print(
            "[BATCH] 过去24小时没有新闻"
        )

        return

    print(
        f"[BATCH] 获取新闻：{len(items)}条"
    )

    print(
        "[BATCH] 使用最新市场数据"
    )

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = make_batch_prompt(
        items,
        current_time,
        market_text
    )

    print(
        f"[BATCH] Prompt长度：{len(prompt)}字符"
    )

    # --------------------------------------------------------
    # 第一次LLM
    # --------------------------------------------------------

    print(
        "[BATCH] 使用DeepSeek..."
    )

    try:

        raw = call_deepseek(
            prompt
        )

    except Exception as e:

        print(
            f"[BATCH] DeepSeek调用失败：{e}"
        )

        return

    print(
        f"[BATCH] LLM返回长度：{len(raw)}字符"
    )

    result = extract_json(
        raw
    )

    if not result:

        print(
            "[BATCH] LLM JSON解析失败"
        )

        return

    # --------------------------------------------------------
    # 检查是否有事件
    # --------------------------------------------------------

    signal = result.get(
        "signal"
    )

    if signal == "NO_CLEAR_EDGE":

        print(
            "[BATCH] LLM判断：没有明确预期差"
        )

        return

    if signal != "ONE_BIG_EVENT":

        print(
            f"[BATCH] 未知signal：{signal}"
        )

        return

    event = result.get(
        "event"
    )

    if not isinstance(event, dict):

        print(
            "[BATCH] 没有有效event"
        )

        return

    print(
        "[BATCH] LLM返回候选事件：1个"
    )

    print(
        "[BATCH] 事件："
        + str(
            event.get(
                "title",
                "unknown"
            )
        )
    )

    # --------------------------------------------------------
    # A股映射
    # --------------------------------------------------------

    if not has_valid_a_share_mapping(
        result
    ):

        result = repair_a_share_mapping(
            result,
            market_text
        )

    # --------------------------------------------------------
    # 最终A股检查
    # --------------------------------------------------------

    if not has_valid_a_share_mapping(
        result
    ):

        print(
            "[BATCH] 最终仍没有明确A股/ETF映射"
        )

        print(
            "[BATCH] 本次不发送"
        )

        return

    # --------------------------------------------------------
    # 提取最终结果
    # --------------------------------------------------------

    event = result["event"]

    idea = event["a_share_idea"]

    scores = result.get(
        "scores",
        {}
    )

    # --------------------------------------------------------
    # 打印最终结果
    # --------------------------------------------------------

    print(
        "[BATCH] ========================================"
    )

    print(
        "[BATCH] FINAL ONE BIG EVENT"
    )

    print(
        f"[BATCH] 标题：{event.get('title', '')}"
    )

    print(
        f"[BATCH] A股标的："
        f"{idea.get('name', '')} "
        f"{idea.get('ticker', '')}"
    )

    print(
        f"[BATCH] 类型："
        f"{idea.get('type', '')}"
    )

    print(
        f"[BATCH] 投资逻辑："
        f"{idea.get('logic', '')}"
    )

    print(
        f"[BATCH] Investment Score："
        f"{scores.get('investment_score', 0)}"
    )

    print(
        "[BATCH] ========================================"
    )

    # --------------------------------------------------------
    # 保存到数据库
    # --------------------------------------------------------

    try:

        save_event(result)

        print(
            "[BATCH] 事件保存成功"
        )

    except Exception as e:

        print(
            f"[BATCH] 事件保存失败：{e}"
        )

    return result


# ============================================================
# 数据库保存
# ============================================================

def save_event(result):

    """
    如果你的db.py已经有保存评分结果的函数，
    可以在这里替换。

    目前为了避免因为数据库接口不同导致主程序失败，
    默认只打印，不强制依赖数据库结构。
    """

    # 如果你的项目原来有：
    #
    # insert_event(...)
    #
    # 可以在这里接入。

    return True
