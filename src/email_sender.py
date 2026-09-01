```python
import smtplib
import json
import html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import *
from .db import get_recent_scored


# ============================================================
# 工具函数
# ============================================================

def safe_float(value, default=0.0):
    """安全转换数字"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_json_load(value, default=None):
    """安全解析JSON"""
    if default is None:
        default = {}

    if value is None:
        return default

    if isinstance(value, (dict, list)):
        return value

    if not isinstance(value, str) or not value.strip():
        return default

    try:
        return json.loads(value)
    except Exception:
        return default


def safe_text(value, default=""):
    """安全转字符串并进行HTML转义"""
    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    return html.escape(text)


def get_a_share_mapping(row):
    """
    获取A股/ETF映射。

    优先级：
    1. strong_linked_a_stocks
    2. affected_assets.a_share
    3. affected_assets.a_shares
    4. 其他兼容结构
    """

    # --------------------------------------------------------
    # 1. 新结构：strong_linked_a_stocks
    # --------------------------------------------------------
    strong_a = safe_json_load(
        row.get("strong_linked_a_stocks", "[]"),
        []
    )

    if isinstance(strong_a, list) and strong_a:
        result = []

        for item in strong_a:
            if not isinstance(item, dict):
                continue

            name = (
                item.get("name")
                or item.get("stock_name")
                or item.get("company")
                or ""
            )

            ticker = (
                item.get("ticker")
                or item.get("code")
                or item.get("symbol")
                or ""
            )

            logic = (
                item.get("logic")
                or item.get("reason")
                or item.get("investment_logic")
                or ""
            )

            directness = (
                item.get("directness")
                or item.get("relationship")
                or item.get("level")
                or ""
            )

            if name or ticker:
                result.append({
                    "name": str(name),
                    "ticker": str(ticker),
                    "logic": str(logic),
                    "directness": str(directness)
                })

        if result:
            return result

    # --------------------------------------------------------
    # 2. 兼容旧结构：affected_assets
    # --------------------------------------------------------
    affected = safe_json_load(
        row.get("affected_assets", "{}"),
        {}
    )

    if not isinstance(affected, dict):
        return []

    # a_share
    a_share = affected.get("a_share")

    if isinstance(a_share, dict):
        name = (
            a_share.get("name")
            or a_share.get("stock_name")
            or ""
        )

        ticker = (
            a_share.get("ticker")
            or a_share.get("code")
            or ""
        )

        logic = (
            a_share.get("logic")
            or a_share.get("investment_logic")
            or ""
        )

        directness = (
            a_share.get("directness")
            or a_share.get("relationship")
            or ""
        )

        if name or ticker:
            return [{
                "name": str(name),
                "ticker": str(ticker),
                "logic": str(logic),
                "directness": str(directness)
            }]

    # --------------------------------------------------------
    # 3. a_shares
    # --------------------------------------------------------
    a_shares = affected.get("a_shares")

    if isinstance(a_shares, list):
        result = []

        for item in a_shares:
            if not isinstance(item, dict):
                continue

            name = (
                item.get("name")
                or item.get("stock_name")
                or ""
            )

            ticker = (
                item.get("ticker")
                or item.get("code")
                or ""
            )

            logic = (
                item.get("logic")
                or item.get("investment_logic")
                or ""
            )

            if name or ticker:
                result.append({
                    "name": str(name),
                    "ticker": str(ticker),
                    "logic": str(logic),
                    "directness": str(
                        item.get("directness", "")
                    )
                })

        if result:
            return result

    return []


def get_event_title(row):
    """
    优先使用事件标题。
    如果batch_scorer没有生成event_title，则使用原新闻标题。
    """

    return (
        row.get("event_title")
        or row.get("title")
        or row.get("event_type")
        or "未知事件"
    )


def get_event_summary(row):
    """
    新闻发生了什么：
    优先使用news_summary，其次rationale。
    """

    return (
        row.get("news_summary")
        or row.get("rationale")
        or row.get("event_type")
        or ""
    )


def get_industry_chain(row):
    """产业链逻辑"""

    return (
        row.get("industry_chain_logic")
        or ""
    )


def get_catalyst(row):
    """未来催化剂"""

    value = row.get("validation_catalyst", "")

    if isinstance(value, list):
        return "；".join(str(x) for x in value)

    return str(value or "")


def get_expectation_gap_detail(row):
    """预期差"""

    return (
        row.get("expectation_gap_detail")
        or ""
    )


def get_price_anomaly(row):
    """价格异常信息"""

    value = row.get("price_anomaly", {})

    if isinstance(value, str):
        value = safe_json_load(value, {})

    if not isinstance(value, dict):
        return {}

    return value


# ============================================================
# 核心：发送邮件
# ============================================================

def send_email():

    print("[MAIL] 开始准备邮件...")

    # --------------------------------------------------------
    # 获取数据库事件
    # --------------------------------------------------------

    rows = get_recent_scored(
        min_score=0,
        limit=100
    )

    if not rows:
        print("[MAIL] 没有评分事件")
        return

    print(f"[MAIL] 数据库返回 {len(rows)} 个事件")

    # --------------------------------------------------------
    # 只保留有明确A股/ETF映射的事件
    #
    # 注意：
    # 不再按照category去重。
    #
    # category只是事件类型，
    # 不能因为两个事件都是technology就删除其中一个。
    # --------------------------------------------------------

    valid_events = []

    for row in rows:

        a_stocks = get_a_share_mapping(row)

        if not a_stocks:
            continue

        # 至少存在一个明确的股票代码/ETF代码
        valid_mapping = False

        for stock in a_stocks:
            ticker = str(stock.get("ticker", "")).strip()
            name = str(stock.get("name", "")).strip()

            if ticker and name:
                valid_mapping = True
                break

        if not valid_mapping:
            continue

        valid_events.append(row)

    print(
        f"[MAIL] 有明确A股/ETF映射："
        f"{len(valid_events)} 个"
    )

    if not valid_events:
        print("[MAIL] 没有符合A股映射要求的事件")
        return

    # --------------------------------------------------------
    # 排序
    #
    # 不再按category去重。
    # 直接按照event_score排序。
    # --------------------------------------------------------

    valid_events.sort(
        key=lambda x: safe_float(
            x.get("event_score", 0)
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # 最终Top 20
    # --------------------------------------------------------

    best_events = valid_events[:20]

    print(
        f"[MAIL] 最终发送 {len(best_events)} 个事件"
    )

    # ========================================================
    # HTML邮件
    # ========================================================

    parts = []

    parts.append("""
    <html>
    <head>
    <meta charset="utf-8">

    <style>

    body {
        font-family:
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            Arial,
            sans-serif;

        color: #222;
        line-height: 1.65;
        background: #f5f6f8;
        margin: 0;
        padding: 20px;
    }

    .container {
        max-width: 1000px;
        margin: auto;
        background: white;
        padding: 25px 35px;
    }

    h1 {
        margin-top: 0;
        font-size: 24px;
        color: #111;
    }

    .subtitle {
        color: #777;
        font-size: 13px;
        margin-bottom: 25px;
    }

    .event {
        border-top: 1px solid #ddd;
        padding: 25px 0;
    }

    .event-title {
        font-size: 19px;
        font-weight: bold;
        margin-bottom: 12px;
    }

    .score {
        font-weight: bold;
        color: #d32f2f;
    }

    .label {
        font-weight: bold;
        color: #444;
    }

    .section {
        margin-top: 12px;
    }

    .stock-box {
        background: #f7f9fc;
        border-left: 4px solid #d32f2f;
        padding: 12px 16px;
        margin-top: 8px;
    }

    .stock-name {
        font-size: 16px;
        font-weight: bold;
    }

    .stock-logic {
        color: #444;
        margin-top: 4px;
    }

    .risk {
        color: #8a1c1c;
    }

    .source {
        margin-top: 15px;
        font-size: 13px;
    }

    .source a {
        color: #1677ff;
        text-decoration: none;
    }

    </style>

    </head>

    <body>

    <div class="container">

    <h1>
    Global Market Event Radar
    </h1>

    <div class="subtitle">
    每日全球重大事件监测 · Top 20 · 过去24小时 · 已筛选A股/ETF映射
    </div>
    """)

    # ========================================================
    # 输出20条
    # ========================================================

    for i, row in enumerate(best_events, 1):

        score = safe_float(
            row.get("event_score", 0)
        )

        novelty = safe_float(
            row.get("novelty", 0)
        )

        impact = safe_float(
            row.get("economic_impact", 0)
        )

        transmission = safe_float(
            row.get("transmission", 0)
        )

        expectation_gap_score = safe_float(
            row.get("expectation_gap", 0)
        )

        sensitivity = safe_float(
            row.get("market_sensitivity", 0)
        )

        direction = (
            row.get("direction")
            or "unknown"
        )

        direction_map = {
            "positive": ("🟢", "利好"),
            "negative": ("🔴", "利空"),
            "mixed": ("🟡", "混合"),
            "unknown": ("⚪", "未知")
        }

        dir_emoji, dir_label = direction_map.get(
            direction,
            ("⚪", "未知")
        )

        category = safe_text(
            row.get("category", "")
        )

        event_type = safe_text(
            row.get("event_type", "")
        )

        title = safe_text(
            get_event_title(row)
        )

        summary = safe_text(
            get_event_summary(row)
        )

        marginal_change = safe_text(
            row.get("marginal_change", "")
        )

        expectation_gap_detail = safe_text(
            get_expectation_gap_detail(row)
        )

        industry_chain = safe_text(
            get_industry_chain(row)
        )

        second_order = safe_text(
            row.get("second_order_effects", "")
        )

        catalyst = safe_text(
            get_catalyst(row)
        )

        risks = safe_text(
            row.get("risks", "")
        )

        source = safe_text(
            row.get("source", "")
        )

        url = html.escape(
            str(row.get("url", "") or ""),
            quote=True
        )

        # ====================================================
        # 事件开始
        # ====================================================

        parts.append(
            f"""
            <div class="event">

                <div class="event-title">
                    {i}. {title}
                    <span class="score">
                        · MEI {score:.0f}
                    </span>
                </div>

                <div>
                    <span class="label">类型：</span>
                    {category}
                    {(" / " + event_type) if event_type else ""}
                </div>

                <div class="section">
                    <span class="label">评分：</span>
                    Novelty {novelty:.0f};
                    Impact {impact:.0f};
                    Transmission {transmission:.0f};
                    Expectation Gap {expectation_gap_score:.0f};
                    Sensitivity {sensitivity:.0f}
                </div>

                <div class="section">
                    <span class="label">
                        {dir_emoji} 方向：
                    </span>
                    {dir_label}
                </div>

                <div class="section">
                    <span class="label">
                        📌 发生了什么：
                    </span>
                    {summary}
                </div>
            """
        )

        # ====================================================
        # 边际变化
        # ====================================================

        if marginal_change:

            parts.append(
                f"""
                <div class="section">
                    <span class="label">
                        🔄 边际变化：
                    </span>
                    {marginal_change}
                </div>
                """
            )

        # ====================================================
        # 预期差
        # ====================================================

        if expectation_gap_detail:

            gap_label = "高"

            if expectation_gap_score < 40:
                gap_label = "低"
            elif expectation_gap_score < 70:
                gap_label = "中"

            parts.append(
                f"""
                <div class="section">
                    <span class="label">
                        📊 预期差：
                    </span>
                    {gap_label}
                    · {expectation_gap_detail}
                </div>
                """
            )

        # ====================================================
        # A股核心标的
        # ====================================================

        a_stocks = get_a_share_mapping(row)

        parts.append(
            """
            <div class="section">
                <span class="label">
                    🇨🇳 强关联A股 / ETF：
                </span>
            """
        )

        # 最多展示3个
        for stock in a_stocks[:3]:

            stock_name = safe_text(
                stock.get("name", "")
            )

            ticker = safe_text(
                stock.get("ticker", "")
            )

            logic = safe_text(
                stock.get("logic", "")
            )

            directness = safe_text(
                stock.get("directness", "")
            )

            parts.append(
                f"""
                <div class="stock-box">

                    <div class="stock-name">
                        {ticker}
                        &nbsp;&nbsp;
                        {stock_name}
                    </div>

                    {
                        f'<div>关联度：{directness}</div>'
                        if directness
                        else ''
                    }

                    {
                        f'<div class="stock-logic">投资逻辑：{logic}</div>'
                        if logic
                        else ''
                    }

                </div>
                """
            )

        parts.append("</div>")

        # ====================================================
        # 产业链
        # ====================================================

        if industry_chain:

            parts.append(
                f"""
                <div class="section">
                    <span class="label">
                        🔗 产业链逻辑：
                    </span>
                    {industry_chain}
                </div>
                """
            )

        # ====================================================
        # 二阶影响
        # ====================================================

        if second_order:

            parts.append(
                f"""
                <div class="section">
                    <span class="label">
                        🔄 二阶影响：
                    </span>
                    {second_order}
                </div>
                """
            )

        # ====================================================
        # 验证催化剂
        # ====================================================

        if catalyst:

            parts.append(
                f"""
                <div class="section">
                    <span class="label">
                        ⏰ 后续验证催化剂：
                    </span>
                    {catalyst}
                </div>
                """
            )

        # ====================================================
        # 风险
        # ====================================================

        if risks:

            parts.append(
                f"""
                <div class="section risk">
                    <span class="label">
                        ⚠️ 风险：
                    </span>
                    {risks}
                </div>
                """
            )

        # ====================================================
        # 原文
        # ====================================================

        if url:

            parts.append(
                f"""
                <div class="source">
                    来源：{source}
                    &nbsp;|&nbsp;
                    <a href="{url}">
                        查看原文
                    </a>
                </div>
                """
            )

        parts.append(
            """
            </div>
            """
        )

    # ========================================================
    # HTML结束
    # ========================================================

    parts.append(
        """
        </div>
        </body>
        </html>
        """
    )

    html_body = "\n".join(parts)

    # ========================================================
    # 创建邮件
    # ========================================================

    msg = MIMEMultipart("alternative")

    msg["Subject"] = (
        f"Global Market Event Radar | "
        f"A股映射Top {len(best_events)}"
    )

    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO

    msg.attach(
        MIMEText(
            html_body,
            "html",
            "utf-8"
        )
    )

    # ========================================================
    # SMTP发送
    # ========================================================

    try:

        with smtplib.SMTP_SSL(
            SMTP_HOST,
            SMTP_PORT
        ) as server:

            server.login(
                SMTP_USER,
                SMTP_PASSWORD
            )

            server.sendmail(
                MAIL_FROM,
                [MAIL_TO],
                msg.as_string()
            )

        print(
            f"[MAIL] 成功发送 "
            f"{len(best_events)} 个事件"
        )

    except Exception as e:

        print(
            f"[MAIL] 邮件发送失败：{e}"
        )


if __name__ == "__main__":
    send_email()
```
