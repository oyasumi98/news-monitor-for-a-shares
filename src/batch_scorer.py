# src/batch_scorer.py

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta

from .db import (
    init_db,
    get_recent_news,
    insert_score,
)
from .config import DB_PATH


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
        base_url=os.getenv(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com"
        )
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
                "role": "system",
                "content": (
                    "你是全球宏观、科技产业、政策和事件驱动投资领域的资深A股策略分析师。"
                    "你的输出必须严格遵守用户要求，只输出合法JSON。"
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1,
        max_tokens=12000
    )

    return response.choices[0].message.content


# ============================================================
# JSON解析
# ============================================================

def extract_json(text):
    """
    尽可能稳健地从LLM返回中提取JSON。
    """

    if not text:
        return None

    text = str(text).strip()

    # --------------------------------------------------------
    # 1. 直接解析
    # --------------------------------------------------------

    try:
        return json.loads(text)
    except Exception:
        pass

    # --------------------------------------------------------
    # 2. 去掉 markdown code block
    # --------------------------------------------------------

    if "```json" in text:
        text = text.replace("```json", "").replace("```", "").strip()

    elif "```" in text:
        text = text.replace("```", "").strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    # --------------------------------------------------------
    # 3. 从第一个 { 到最后一个 }
    # --------------------------------------------------------

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:

        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    # --------------------------------------------------------
    # 4. 从第一个 [ 到最后一个 ]
    # --------------------------------------------------------

    start = text.find("[")
    end = text.rfind("]")

    if start >= 0 and end > start:

        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    # --------------------------------------------------------
    # 5. 修复尾随逗号
    # --------------------------------------------------------

    try:
        import re

        fixed = re.sub(
            r",\s*([}\]])",
            r"\1",
            text
        )

        start = fixed.find("{")
        end = fixed.rfind("}")

        if start >= 0 and end > start:
            return json.loads(
                fixed[start:end + 1]
            )

    except Exception:
        pass

    print("[BATCH] JSON解析失败")
    print(
        "[BATCH] LLM原始返回前1000字符："
        + text[:1000]
    )

    return None


# ============================================================
# 新闻文本
# ============================================================

def build_news_text(items):

    blocks = []

    for i, item in enumerate(items):

        news_id = item.get("id", "")

        source = item.get(
            "source",
            "unknown"
        )

        published = item.get(
            "published"
            or "collected_at",
            "unknown"
        )

        title = item.get(
            "title",
            ""
        )

        summary = item.get(
            "summary",
            ""
        )

        content = item.get(
            "content",
            ""
        )

        url = item.get(
            "url",
            ""
        )

        # 防止prompt无限膨胀
        content = str(content)[:1200]

        blocks.append(
            f"""
NEWS_ID: {news_id}
SOURCE: {source}
PUBLISHED: {published}
TITLE: {title}
SUMMARY: {summary}
CONTENT: {content}
URL: {url}
"""
        )

    return "\n".join(blocks)


# ============================================================
# 核心Prompt
# ============================================================

def make_batch_prompt(
    items,
    current_time,
    market_text
):

    news_text = build_news_text(items)

    return f"""
你是一名拥有15年以上经验的全球宏观、科技产业和A股事件驱动策略分析师。

当前时间：
{current_time}

============================================================
核心任务
============================================================

从过去24小时发生的新闻中，寻找：

【20个最值得A股投资者关注的重大边际变化事件】

最终必须输出20条。

不是简单寻找20条热门新闻。

真正要寻找的是：

新信息
+
预期差
+
基本面影响
+
产业链传导
+
明确A股映射
+
未来可能继续演绎

============================================================
一、时间限制
============================================================

严格限制在过去24小时。

核心事件必须发生在过去24小时。

旧新闻再次报道：

淘汰。

如果新闻只是对过去事件的重复报道：

淘汰。

如果新闻标题不同，但实际上描述的是同一件事情：

必须合并。

例如：

“30年美债收益率创高位”

“全球长期融资成本上升”

“美国财政赤字担忧”

如果本质由同一个驱动因素造成：

只能算一个事件。

============================================================
二、事件级去重
============================================================

特别注意：

不要按照新闻标题去重。

必须按照：

【核心事实 + 核心驱动因素 + 核心经济影响】

判断是不是同一个事件。

例如：

A媒体：
美国财政部扩大长期国债回购。

B媒体：
美国30年期美债收益率下降。

C媒体：
黄金上涨。

如果三者本质都是因为：

美国财政部扩大长期国债回购

那么只能保留一个核心事件。

但：

美国财政部扩大回购

和

美联储官员突然改变降息表态

属于两个不同事件。

============================================================
三、20条事件必须有差异
============================================================

最终20条不能全部来自同一个主题。

尽量覆盖：

宏观
政策
科技
AI
半导体
机器人
新能源
能源
化工
农业
有色金属
医药
消费
金融
航运
军工
地产
制造业
产业链
重要人物观点

但不是为了凑类别。

如果某个行业没有真正有价值的事件：

可以不选。

============================================================
四、政策新闻限制
============================================================

政策类事件：

原则上最多3条。

除非过去24小时出现真正不同且重大的一组政策变化。

不要把：

央行政策
财政政策
产业政策
监管政策

写成大量相似新闻。

============================================================
五、重点寻找“预期差”
============================================================

每条事件必须回答：

市场原来认为：

什么？

现在突然发生了：

什么？

因此市场可能需要：

重新定价什么？

重点寻找：

1. 新闻重大，但A股相关股票没有明显上涨；

2. 新闻没有特别热门，但可能改变未来盈利；

3. 产业链上游出现供给变化；

4. 下游需求突然变化；

5. 大客户资本开支变化；

6. 新订单；

7. 新产能；

8. 产品价格变化；

9. 库存变化；

10. 技术突破；

11. 重要公司CEO突然改变表态；

12. 重要投资人/产业人物发表与基本面有关的重要观点；

13. 海外公司变化可能传导到中国产业链；

14. 一个冷门事件可能成为未来1个月的主线。

============================================================
六、重要人物观点
============================================================

必须关注：

CEO
CFO
产业专家
科学家
经济学家
央行官员
政府官员
基金经理
知名投资人
产业链核心人物

但是：

普通评论不要。

必须是：

能够改变市场对行业基本面判断的观点。

区分：

FACT
事实

GUIDANCE
指引/预测

OPINION
观点

============================================================
七、科技产业链
============================================================

科技事件必须尽量深入产业链。

例如：

AI资本开支

↓

GPU

↓

HBM

↓

先进封装

↓

光模块

↓

PCB

↓

服务器

↓

电力

↓

数据中心

不能只写：

“AI利好科技股”。

必须找到：

哪个具体环节的订单、价格、产能、收入或者利润可能变化。

============================================================
八、A股映射
============================================================

这是硬性条件。

20条最终事件：

【必须全部有明确A股股票或者A股ETF】

不能：

纯概念。

不能：

“AI相关股票”。

不能：

“机器人板块”。

必须给：

公司名称
+
6位股票代码

或者：

ETF名称
+
ETF代码

优先级：

DIRECT
>
INDIRECT
>
SECOND_ORDER

如果一个事件完全找不到真实A股映射：

不要输出。

但是：

不要为了有股票而强行找概念股。

============================================================
九、A股标的必须解释
============================================================

必须解释：

事件

↓

产业链变化

↓

公司收入/订单/成本/产能/利润

↓

估值

↓

股价

至少形成完整逻辑。

例如：

美国数据中心资本开支增加

↓

光模块需求增加

↓

800G/1.6T需求增长

↓

中际旭创海外客户订单增长

↓

收入和利润预期上修

↓

估值可能重新定价

这种才算有效映射。

============================================================
十、结合最新行情
============================================================

必须使用以下最新市场数据：

{market_text}

重点判断：

1. A股标的最近涨跌幅；

2. 是否连续上涨；

3. 是否已经大幅上涨；

4. 是否已经成为市场热点；

5. 是否已经明显拥挤；

6. 新闻发生后股票是否没有反应；

7. 新闻基本面影响是否明显大于股价反应。

尤其关注：

【基本面变化 > 股价变化】

这种事件。

它往往比：

新闻很好 + 股票已经暴涨

更有投资价值。

============================================================
十一、股票表现不能张冠李戴
============================================================

绝对禁止：

把WMT的跌幅解释成美债事件。

把MU上涨解释成机器人事件。

把XOM上涨解释成农业事件。

每个股票表现：

必须对应这个股票自己的真实行情。

如果市场数据中没有该股票：

写：

unknown

不能编造。

============================================================
十二、最终排序
============================================================

按照：

预期差
+
基本面影响
+
产业链传导
+
A股映射强度
+
未来催化剂

综合排序。

不是按照：

新闻热度。

不是按照：

媒体报道数量。

不是按照：

股票当前涨幅。

============================================================
十三、必须输出20条
============================================================

最终必须：

20条。

不能1条。

不能5条。

不能10条。

不能因为某些新闻不够好就只输出3条。

但：

每一条必须满足：

过去24小时
+
非重复事件
+
真实边际变化
+
明确A股股票/ETF
+
真实投资逻辑

如果高质量事件不足：

可以降低事件重要性标准，

但不能降低：

时间要求
去重要求
A股映射要求
真实性要求。

============================================================
十四、输出格式
============================================================

只输出JSON：

{{
    "signal": "TWENTY_EVENTS",

    "events": [
        {{
            "rank": 1,

            "title": "",

            "category":
            "macro|policy|technology|company|industry_chain|science|market_event",

            "event_cluster": "",

            "published_time": "",

            "source_news_ids": [],

            "news_summary": "",

            "what_changed": "",

            "why_now": "",

            "market_consensus": "",

            "expectation_gap": "high|medium|low",

            "expectation_gap_detail": "",

            "market_price_reaction": "",

            "industry_chain_logic": "",

            "a_share_idea": {{
                "name": "",
                "ticker": "",
                "type": "stock|ETF",
                "logic": "",
                "directness":
                "DIRECT|INDIRECT|SECOND_ORDER"
            }},

            "us_reference": [],

            "speaker": {{
                "name": null,
                "role": null,
                "statement_type": null,
                "core_view": null
            }},

            "investment_thesis": "",

            "future_1_4_weeks": "",

            "key_catalysts": [],

            "key_risks": [],

            "investment_score": 0
        }}
    ]
}}

============================================================
十五、字段要求
============================================================

news_summary：

用一句话简单说明发生了什么。

what_changed：

必须明确说明：

“昨天和今天相比，新增了什么？”

investment_thesis：

说明为什么可能影响A股。

future_1_4_weeks：

说明未来1-4周可能怎么演绎。

investment_score：

0-100。

参考：

90-100：
非常强的预期差，可能形成阶段性行情。

80-89：
较强预期差。

70-79：
值得关注。

60-69：
一般。

<60：

不要进入最终20条。

============================================================
十六、绝对禁止
============================================================

禁止：

编造新闻。

编造股票。

编造股票代码。

编造价格。

编造涨跌幅。

编造人物观点。

编造产业链关系。

重复事件。

旧新闻。

纯概念映射。

============================================================
新闻数据
============================================================

{news_text}

============================================================
最新市场数据
============================================================

{market_text}

只返回JSON。
"""


# ============================================================
# A股映射检查
# ============================================================

def has_valid_a_share_mapping(event):

    if not isinstance(event, dict):
        return False

    idea = event.get(
        "a_share_idea",
        {}
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
        "不确定",
        "无法确定"
    }

    if name.lower() in invalid:
        return False

    if ticker.lower() in invalid:
        return False

    if not logic:
        return False

    # 必须有6位A股代码
    digits = (
        ticker
        .replace(".SH", "")
        .replace(".SZ", "")
        .replace(".BJ", "")
        .replace("SH", "")
        .replace("SZ", "")
        .replace("BJ", "")
    )

    if not digits.isdigit():
        return False

    if len(digits) != 6:
        return False

    return True


# ============================================================
# 事件去重
# ============================================================

def normalize_event_key(event):

    """
    用事件标题 + 事件聚类做基础去重。
    """

    title = str(
        event.get("title", "")
    ).lower().strip()

    cluster = str(
        event.get("event_cluster", "")
    ).lower().strip()

    text = f"{cluster}|{title}"

    # 删除常见标点
    for char in (
        " ",
        "，",
        "。",
        "、",
        "：",
        ":",
        "！",
        "!",
        "？",
        "?",
        "-",
        "_",
        "/"
    ):
        text = text.replace(
            char,
            ""
        )

    return text[:150]


def deduplicate_events(events):

    """
    第一层事件级去重。

    同一个 event_cluster 只保留最高分。
    """

    cluster_best = {}

    for event in events:

        if not isinstance(
            event,
            dict
        ):
            continue

        cluster = str(
            event.get(
                "event_cluster",
                ""
            )
        ).strip()

        if not cluster:
            cluster = normalize_event_key(
                event
            )

        score = float(
            event.get(
                "investment_score",
                0
            ) or 0
        )

        if (
            cluster not in cluster_best
            or score >
            float(
                cluster_best[cluster].get(
                    "investment_score",
                    0
                )
            )
        ):
            cluster_best[cluster] = event

    return list(
        cluster_best.values()
    )


# ============================================================
# 新闻ID匹配
# ============================================================

def find_news_id_for_event(
    event,
    items
):

    source_ids = event.get(
        "source_news_ids",
        []
    )

    if isinstance(
        source_ids,
        list
    ):

        for news_id in source_ids:

            try:
                return int(news_id)
            except Exception:
                pass

    title = str(
        event.get(
            "title",
            ""
        )
    ).lower()

    # 关键词匹配
    keywords = [
        x.strip()
        for x in title.replace(
            "：",
            " "
        ).split()
        if len(x.strip()) >= 2
    ]

    best_id = None
    best_score = 0

    for item in items:

        item_title = str(
            item.get(
                "title",
                ""
            )
        ).lower()

        score = 0

        for keyword in keywords:

            if keyword in item_title:
                score += len(keyword)

        if score > best_score:

            best_score = score

            best_id = item.get(
                "id"
            )

    return best_id


# ============================================================
# 保存事件
# ============================================================

def save_event(
    event,
    rss_item_id
):

    if rss_item_id is None:
        return False

    idea = event.get(
        "a_share_idea",
        {}
    )

    score = float(
        event.get(
            "investment_score",
            0
        ) or 0
    )

    score_data = {

        "category":
        event.get(
            "category",
            "other"
        ),

        "event_type":
        event.get(
            "event_cluster",
            event.get(
                "title",
                ""
            )
        )[:100],

        "novelty":
        event.get(
            "expectation_gap",
            "medium"
        ) == "high"
        and 90
        or 70,

        "economic_impact":
        score,

        "transmission":
        80,

        "expectation_gap":
        {
            "high": 90,
            "medium": 65,
            "low": 40
        }.get(
            event.get(
                "expectation_gap",
                "low"
            ),
            50
        ),

        "market_sensitivity":
        70,

        "event_score":
        score,

        "direction":
        "positive",

        "affected_assets":
        json.dumps(
            {
                "a_share_idea":
                idea,

                "us_reference":
                event.get(
                    "us_reference",
                    []
                )
            },
            ensure_ascii=False
        ),

        "affected_industries":
        event.get(
            "category",
            ""
        ),

        "rationale":
        event.get(
            "investment_thesis",
            ""
        ),

        "second_order_effects":
        event.get(
            "future_1_4_weeks",
            ""
        ),

        "risks":
        "\n".join(
            event.get(
                "key_risks",
                []
            )
        ),

        "model":
        "deepseek-20-events",

        "scored_at":
        datetime.now(
            timezone.utc
        ).isoformat()
    }

    insert_score(
        rss_item_id,
        score_data
    )

    return True


# ============================================================
# 政策数量控制
# ============================================================

def limit_policy_events(
    events,
    max_policy=3
):

    policy_events = []

    non_policy_events = []

    for event in events:

        category = str(
            event.get(
                "category",
                ""
            )
        ).lower()

        if category == "policy":
            policy_events.append(
                event
            )
        else:
            non_policy_events.append(
                event
            )

    policy_events.sort(
        key=lambda x: float(
            x.get(
                "investment_score",
                0
            ) or 0
        ),
        reverse=True
    )

    return (
        non_policy_events
        +
        policy_events[:max_policy]
    )


# ============================================================
# 最终事件选择
# ============================================================

def select_final_events(
    events,
    target=20
):

    # --------------------------------------------------------
    # 1. 只保留有效A股映射
    # --------------------------------------------------------

    valid = [
        event
        for event in events
        if has_valid_a_share_mapping(
            event
        )
    ]

    print(
        f"[BATCH] 有效A股映射："
        f"{len(valid)}/{len(events)}"
    )

    # --------------------------------------------------------
    # 2. 事件去重
    # --------------------------------------------------------

    valid = deduplicate_events(
        valid
    )

    print(
        f"[BATCH] 事件级去重后："
        f"{len(valid)}条"
    )

    # --------------------------------------------------------
    # 3. 政策最多3条
    # --------------------------------------------------------

    valid = limit_policy_events(
        valid,
        max_policy=3
    )

    # --------------------------------------------------------
    # 4. 按投资评分排序
    # --------------------------------------------------------

    valid.sort(
        key=lambda x: float(
            x.get(
                "investment_score",
                0
            ) or 0
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # 5. 取20条
    # --------------------------------------------------------

    final = valid[:target]

    # --------------------------------------------------------
    # 6. 重新编号
    # --------------------------------------------------------

    for i, event in enumerate(
        final,
        1
    ):
        event["rank"] = i

    return final


# ============================================================
# 主函数
# ============================================================

def run_batch(
    market_text="unknown",
    current_time=None
):

    print(
        "[BATCH] ===== GLOBAL MARKET EVENT RADAR ====="
    )

    init_db()

    if current_time is None:

        current_time = datetime.now(
            timezone.utc
        ).isoformat()

    print(
        f"[BATCH] 当前时间："
        f"{current_time}"
    )

    print(
        "[BATCH] 时间窗口：过去24小时"
    )

    # --------------------------------------------------------
    # 获取新闻
    # --------------------------------------------------------

    try:

        items = get_recent_news(
            hours=24
        )

    except Exception as e:

        print(
            f"[BATCH] 获取新闻失败：{e}"
        )

        return None

    if not items:

        print(
            "[BATCH] 过去24小时没有新闻"
        )

        return None

    print(
        f"[BATCH] 获取新闻："
        f"{len(items)}条"
    )

    # --------------------------------------------------------
    # 市场数据
    # --------------------------------------------------------

    if market_text != "unknown":

        print(
            "[BATCH] 使用最新市场数据"
        )

    else:

        print(
            "[BATCH] 市场数据不可用"
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
        f"[BATCH] Prompt长度："
        f"{len(prompt)}字符"
    )

    # --------------------------------------------------------
    # LLM
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
            f"[BATCH] DeepSeek调用失败："
            f"{e}"
        )

        return None

    print(
        f"[BATCH] LLM返回长度："
        f"{len(raw)}字符"
    )

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    result = extract_json(
        raw
    )

    if not result:

        print(
            "[BATCH] LLM JSON解析失败"
        )

        return None

    if not isinstance(
        result,
        dict
    ):

        print(
            "[BATCH] LLM返回不是JSON对象"
        )

        return None

    # --------------------------------------------------------
    # 获取候选
    # --------------------------------------------------------

    candidates = result.get(
        "events",
        []
    )

    if not isinstance(
        candidates,
        list
    ):

        print(
            "[BATCH] events不是数组"
        )

        return None

    print(
        f"[BATCH] LLM返回候选："
        f"{len(candidates)}条"
    )

    # --------------------------------------------------------
    # 最终筛选
    # --------------------------------------------------------

    final_events = select_final_events(
        candidates,
        target=20
    )

    print(
        f"[BATCH] 最终事件："
        f"{len(final_events)}条"
    )

    # --------------------------------------------------------
    # 如果不足20条
    # --------------------------------------------------------

    if len(final_events) < 20:

        print(
            f"[BATCH] 警告："
            f"只有{len(final_events)}条有效事件，"
            f"不足20条"
        )

    # --------------------------------------------------------
    # 保存
    # --------------------------------------------------------

    saved_count = 0

    for event in final_events:

        rss_item_id = find_news_id_for_event(
            event,
            items
        )

        if rss_item_id is None:

            print(
                "[BATCH] 无法匹配新闻ID："
                + str(
                    event.get(
                        "title",
                        ""
                    )
                )[:60]
            )

            continue

        try:

            ok = save_event(
                event,
                rss_item_id
            )

            if ok:

                saved_count += 1

                idea = event.get(
                    "a_share_idea",
                    {}
                )

                print(
                    f"[BATCH] "
                    f"{event.get('rank')}. "
                    f"{event.get('title', '')[:50]} "
                    f"| "
                    f"{idea.get('name', '')} "
                    f"{idea.get('ticker', '')} "
                    f"| "
                    f"Score="
                    f"{event.get('investment_score', 0)}"
                )

        except Exception as e:

            print(
                f"[BATCH] 保存事件失败："
                f"{e}"
            )

    print(
        f"[BATCH] 成功保存："
        f"{saved_count}/{len(final_events)}"
    )

    return {
        "signal":
        "TWENTY_EVENTS",

        "events":
        final_events
    }
