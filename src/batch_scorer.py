# src/batch_scorer.py

import json
import os
from datetime import datetime, timezone

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
        temperature=0.15,
        max_tokens=12000
    )

    return response.choices[0].message.content


# ============================================================
# JSON解析
# ============================================================

def extract_json(text):

    if not text:
        return None

    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if len(lines) >= 3:
            lines = lines[1:]

            if lines[-1].strip().startswith("```"):
                lines = lines[:-1]

            text = "\n".join(lines).strip()

    try:
        return json.loads(text)

    except Exception:
        pass

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
# 新闻Prompt
# ============================================================

def make_batch_prompt(
    items,
    current_time,
    market_text
):

    news_blocks = []

    for i, item in enumerate(items):

        news_id = item.get(
            "id",
            i
        )

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

        title = item.get(
            "title",
            ""
        )

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

==========================================
"""
        )

    news_text = "\n".join(
        news_blocks
    )

    return f"""

你是一名拥有10年以上经验的全球宏观、科技产业、
商品、政策和A股事件驱动策略分析师。

你的任务不是寻找“最热门新闻”。

你的任务是：

从过去24小时全球新闻中，
寻找20个彼此独立、具有明确A股交易映射、
并且未来1～4周可能产生市场影响的重大事件。

============================================================
当前时间
============================================================

{current_time}

============================================================
核心目标
============================================================

最终输出：

TOP 20 GLOBAL MARKET EVENTS

必须满足：

1. 每个事件必须是过去24小时出现的新信息。

2. 同一个事件的不同媒体报道必须合并。

3. 标题不同但本质相同，必须视为同一个事件。

4. 不允许为了凑20条，把同一个事件拆成多个事件。

5. 每个事件必须存在明确的A股上市公司或者A股ETF映射。

6. 不允许纯概念映射。

7. 优先选择DIRECT关系。

8. 如果不存在DIRECT，可以使用INDIRECT。

9. 如果只有ETF能够准确表达，则可以使用ETF。

10. 禁止为了凑数量而编造股票。

============================================================
一、时间限制
============================================================

严格限制：

过去24小时。

如果只是：

旧新闻重新报道
旧观点重复传播
旧政策再次解读
旧数据再次分析

必须淘汰。

重点寻找：

新数据
新订单
新产能
新融资
新资本开支
新技术
新产品
新政策
新监管
新价格
新供需变化
新事故
新制裁
新并购
新IPO
新财报
重要人物最新表态
产业链最新变化

============================================================
二、新闻去重
============================================================

这是最重要的要求之一。

你必须进行“事件级去重”。

例如：

新闻A：
美国30年国债收益率创多年新高

新闻B：
全球长期融资成本创新高

新闻C：
美国财政赤字推动长期利率上升

如果三者核心驱动因素相同：

必须合并成：

“美国长期国债收益率持续上行”

不能输出3条。

同样：

新闻A：
Unitree上市大涨

新闻B：
中国人形机器人公司上市

新闻C：
机器人IPO受到市场追捧

如果本质上都是同一个事件：

必须合并。

============================================================
三、事件必须“真正不同”
============================================================

20个事件必须尽可能分散。

不要出现：

10条美债新闻
8条AI新闻
6条油价新闻

应该尽可能覆盖：

宏观
政策
科技
AI
半导体
能源
化工
有色
农业
医药
机器人
消费
汽车
航运
金融
地产
军工
地缘政治
商品
产业链

但不是机械要求平均分配。

如果某一天科技事件明显更多，可以增加科技事件。

============================================================
四、特别关注产业链
============================================================

科技产业链是重点。

尤其关注：

AI
GPU
HBM
先进封装
服务器
光模块
PCB
液冷
数据中心
电力设备
半导体设备
半导体材料
机器人
自动驾驶
智能汽车
人形机器人
工业软件
通信
卫星
能源科技

必须尽量向产业链下游继续推演。

例如：

AI资本开支增加

↓

GPU需求

↓

HBM需求

↓

先进封装

↓

光模块

↓

PCB

↓

液冷

↓

电力设备

最终判断：

哪个环节的盈利预期最可能发生变化。

============================================================
五、政策事件
============================================================

政策新闻重要，但不能占据全部结果。

正常情况下：

政策类事件最多4条。

如果出现重大政策密集发布，可以适当增加。

但是：

同一个政策主题必须合并。

例如：

央行降息
央行释放宽松信号
市场提高降息预期

如果本质属于同一政策变化：

合并。

============================================================
六、重要人物发言
============================================================

特别关注：

企业CEO
科技公司创始人
央行官员
财政部长
重要政府官员
行业协会负责人
知名投资人
重要分析师
产业链核心企业负责人

但必须区分：

FACT
GUIDANCE
OPINION

尤其关注：

与产业链
资本开支
订单
需求
产能
产品
技术路线
价格

直接相关的发言。

纯政治评论、情绪表达、没有基本面意义的观点：

淘汰。

============================================================
七、A股映射
============================================================

这是硬性条件。

每个事件必须至少找到：

一个A股上市公司

或者：

一个A股ETF。

优先级：

DIRECT
>
INDIRECT
>
SECOND_ORDER

禁止：

纯概念
蹭热点
业务关系非常弱
仅仅因为名字相似

必须说明：

事件

↓

产业链变化

↓

公司收入/订单/成本/产能/利润

↓

估值变化

↓

股价可能变化

============================================================
八、A股标的选择原则
============================================================

优先：

1. 业务直接受影响的公司

2. 核心供应商

3. 核心客户

4. 行业龙头

5. 盈利弹性大的公司

6. 市场关注度高但尚未充分交易的公司

如果个股无法准确映射：

可以使用ETF。

ETF必须能够准确代表这个事件。

============================================================
九、最新行情
============================================================

下面是最新市场数据：

{market_text}

必须使用最新行情。

重点判断：

1. A股标的最近涨跌幅

2. 是否已经连续上涨

3. 是否已经大幅上涨

4. 是否明显拥挤

5. 新闻是否已经被股价交易

6. 新闻重大程度和股价反应是否匹配

尤其寻找：

“基本面变化很大，但A股相关股票没有明显上涨”

这类事件通常具有更高预期差。

============================================================
十、预期差
============================================================

不要简单把“重大新闻”当成“高分新闻”。

重点寻找：

市场原有预期

VS

最新事实

之间的差异。

例如：

市场认为：
AI资本开支开始放缓

最新事实：
核心企业继续大幅增加资本开支

这种：

基本面变化 > 市场预期

属于高预期差。

反过来：

市场已经暴涨

但新闻只是符合预期

属于低预期差。

============================================================
十一、未来1～4周
============================================================

每个事件必须寻找：

未来1～4周可能验证逻辑的催化剂。

例如：

财报
订单
价格
库存
产量
政策
会议
产品发布
技术验证
资本开支
产能投产
出口数据
产业数据

如果没有明确催化剂：

降低评分。

============================================================
十二、评分体系
============================================================

每个事件评分：

novelty：
信息新颖度

economic_impact：
经济/行业/盈利影响

transmission：
产业链传导能力

expectation_gap：
预期差

market_mispricing：
基本面变化与股价反应之间的错配

a_share_mapping：
A股映射强度

catalyst_strength：
未来催化强度

最终：

investment_score

不是单纯选择最热门事件。

============================================================
十三、最终排序
============================================================

先找到：

30～50个候选事件。

然后：

去重
→
A股映射验证
→
行情验证
→
预期差评分
→
产业链分析
→
未来催化分析

最终选择TOP 20。

============================================================
十四、重要约束
============================================================

必须输出20个事件。

但是：

如果某事件无法找到可靠A股/ETF：

不要编造。

如果真正符合条件的事件不足20个：

可以输出少于20个。

但目标是尽可能接近20个。

============================================================
输出格式
============================================================

只返回JSON。

格式：

{{
    "signal": "TOP_20_EVENTS",

    "events": [

        {{
            "rank": 1,

            "title": "",

            "category": "",

            "event_cluster": "",

            "published_time": "",

            "source_news_ids": [],

            "news_summary": "",

            "what_changed": "",

            "why_now": "",

            "market_consensus": "",

            "expectation_gap_detail": "",

            "market_price_reaction": "",

            "market_mispricing": "",

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

            "direction": "positive|negative|mixed",

            "scores": {{

                "novelty": 0,
                "economic_impact": 0,
                "transmission": 0,
                "expectation_gap": 0,
                "market_mispricing": 0,
                "a_share_mapping": 0,
                "catalyst_strength": 0,
                "investment_score": 0

            }}

        }}

    ]

}}

============================================================
最终硬性要求
============================================================

1. 只返回JSON。

2. 最多20个事件。

3. 目标20个事件。

4. 每个事件必须是独立事件。

5. 同一事件不同媒体报道必须合并。

6. 不允许标题不同但本质相同的事件重复出现。

7. 每个事件必须有明确A股股票或ETF。

8. 不允许纯概念映射。

9. 必须考虑最新行情。

10. 必须考虑预期差。

11. 必须分析产业链。

12. 必须给出未来1～4周催化剂。

13. 政策事件正常情况下不超过4条。

14. 科技和产业链事件优先深入分析。

15. 重要产业链人物发言可以作为独立事件，但必须存在新的基本面信息。

16. 不得编造公司、股票代码、ETF。

17. 不得使用24小时以前的旧事件作为核心事件。

18. 同一个产业链连续出现多个高度相关事件时，应合并。

============================================================
过去24小时新闻
============================================================

{news_text}

"""


# ============================================================
# A股映射检查
# ============================================================

def get_events(result):

    if not isinstance(result, dict):
        return []

    events = result.get(
        "events",
        []
    )

    if not isinstance(events, list):
        return []

    return events


def has_valid_a_share_mapping(event):

    if not isinstance(event, dict):
        return False

    idea = event.get(
        "a_share_idea"
    )

    if not isinstance(idea, dict):
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

    if len(logic) < 10:
        return False

    return True


# ============================================================
# A股映射二次修复
# ============================================================

def make_mapping_repair_prompt(
    event,
    market_text
):

    return f"""

你是一名A股产业链研究员。

现在已经确定下面这个全球事件。

你的任务不是重新判断事件是否重要。

你的唯一任务：

为这个事件寻找最直接、最可靠的A股上市公司或者A股ETF。

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

必须：

1. 找真实存在的A股上市公司或者A股ETF。

2. 不允许纯概念股。

3. 优先DIRECT。

4. 必须解释：

事件
↓
产业链
↓
公司收入/订单/成本/盈利
↓
估值
↓
股价

5. 必须考虑当前股价。

6. 如果股票已经大幅上涨，需要说明是否已经price in。

7. 如果没有可靠映射，返回null。

============================================================
输出
============================================================

只返回JSON：

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

"""


def repair_a_share_mapping(
    event,
    market_text
):

    try:

        print(
            "[BATCH] 启动A股映射二次分析..."
        )

        prompt = make_mapping_repair_prompt(
            event,
            market_text
        )

        response = call_deepseek(
            prompt
        )

        repaired = extract_json(
            response
        )

        if not repaired:
            return event

        mapping = repaired.get(
            "a_share_idea"
        )

        if not isinstance(mapping, dict):
            return event

        event["a_share_idea"] = mapping

        print(
            "[BATCH] A股映射补全："
            f"{mapping.get('name', '')} "
            f"{mapping.get('ticker', '')}"
        )

        return event

    except Exception as e:

        print(
            f"[BATCH] A股映射修复失败：{e}"
        )

        return event


# ============================================================
# 主流程
# ============================================================

def run_batch(
    market_text="unknown",
    current_time=None
):

    print(
        "[BATCH] ===== GLOBAL MARKET EVENT RADAR ====="
    )

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

    # ========================================================
    # 获取新闻
    # ========================================================

    try:

        items = get_recent_news(
            hours=24,
            limit=200
        )

    except Exception as e:

        print(
            f"[BATCH] 获取新闻失败：{e}"
        )

        return []

    if not items:

        print(
            "[BATCH] 过去24小时没有新闻"
        )

        return []

    print(
        f"[BATCH] 获取新闻：{len(items)}条"
    )

    print(
        "[BATCH] 使用最新市场数据"
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
        f"[BATCH] Prompt长度：{len(prompt)}字符"
    )

    # ========================================================
    # LLM
    # ========================================================

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

        return []

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

        return []

    events = get_events(
        result
    )

    print(
        f"[BATCH] LLM返回候选事件：{len(events)}个"
    )

    if not events:

        print(
            "[BATCH] 没有候选事件"
        )

        return []

    # ========================================================
    # A股映射二次验证
    # ========================================================

    valid_events = []

    for event in events:

        if not has_valid_a_share_mapping(
            event
        ):

            print(
                "[BATCH] 事件缺少有效A股映射："
                f"{event.get('title', '')}"
            )

            event = repair_a_share_mapping(
                event,
                market_text
            )

        if not has_valid_a_share_mapping(
            event
        ):

            print(
                "[BATCH] 淘汰：没有可靠A股/ETF映射"
            )

            continue

        valid_events.append(
            event
        )

    # ========================================================
    # 排序
    # ========================================================

    def score_key(event):

        scores = event.get(
            "scores",
            {}
        )

        try:

            return float(
                scores.get(
                    "investment_score",
                    0
                )
            )

        except Exception:

            return 0

    valid_events.sort(
        key=score_key,
        reverse=True
    )

    # ========================================================
    # 最多20条
    # ========================================================

    final_events = valid_events[:20]

    # ========================================================
    # 重新编号
    # ========================================================

    for index, event in enumerate(
        final_events,
        start=1
    ):

        event["rank"] = index

    print(
        "[BATCH] ========================================"
    )

    print(
        f"[BATCH] FINAL EVENTS：{len(final_events)}个"
    )

    for event in final_events:

        idea = event.get(
            "a_share_idea",
            {}
        )

        scores = event.get(
            "scores",
            {}
        )

        print(
            f"[BATCH] "
            f"{event.get('rank', '')}. "
            f"{event.get('title', '')}"
        )

        print(
            "[BATCH] A股："
            f"{idea.get('name', '')} "
            f"{idea.get('ticker', '')}"
        )

        print(
            "[BATCH] Score："
            f"{scores.get('investment_score', 0)}"
        )

    print(
        "[BATCH] ========================================"
    )

    # ========================================================
    # 保存
    # ========================================================

    saved = 0

    for event in final_events:

        try:

            save_event(
                event
            )

            saved += 1

        except Exception as e:

            print(
                f"[BATCH] 保存事件失败：{e}"
            )

    print(
        f"[BATCH] 事件保存完成：{saved}条"
    )

    return final_events


# ============================================================
# 数据库保存
# ============================================================

def save_event(event):

    """
    当前版本只保留接口。

    下一步修改 db.py 时，
    会把这里正式接入 event_scores。
    """

    return True
