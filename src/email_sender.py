import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from .config import *
from .db import get_recent_scored


def send_email():
    rows = get_recent_scored(MIN_SCORE_TO_EMAIL, MAX_EMAIL_EVENTS)
    if not rows:
        print("[MAIL] no events over threshold")
        return

    parts = ["<html><body><h2>Global Market Event Radar</h2>"]
    for i, row in enumerate(rows, 1):
        r = dict(row)

        def to_float(val, default=0.0):
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        score = to_float(r.get("event_score"))
        novelty = to_float(r.get("novelty"))
        impact = to_float(r.get("economic_impact"))
        trans = to_float(r.get("transmission"))
        gap = to_float(r.get("expectation_gap"))
        sens = to_float(r.get("market_sensitivity"))

        # ---- 方向（利好/利空） ----
        direction = r.get("direction", "unknown")
        direction_emoji = {"positive": "🟢", "negative": "🔴", "mixed": "🟡", "unknown": "⚪"}.get(direction, "⚪")
        direction_label = {"positive": "利好", "negative": "利空", "mixed": "混合", "unknown": "未知"}.get(direction, "未知")

        # ============================================================
        # 关键修复：从 affected_assets JSON 中解析扩展信息
        # ============================================================
        affected_raw = r.get("affected_assets", "{}")
        try:
            extra = json.loads(affected_raw) if isinstance(affected_raw, str) else {}
        except:
            extra = {}

        # ---- A股映射 ----
        a_share = extra.get("a_share", {})
        a_share_name = a_share.get("name", "")
        a_share_ticker = a_share.get("ticker", "")
        a_share_logic = a_share.get("logic", "")
        a_share_directness = a_share.get("directness", "")

        # ---- 美股参考 ----
        us_reference = extra.get("us_reference", [])

        # ---- 预期差详细 ----
        exp_gap_detail = extra.get("expectation_gap_detail", "")
        exp_gap_label = {"high": "高", "medium": "中", "low": "低"}.get(
            r.get("expectation_gap", "unknown"), "未知"
        )

        # ---- 催化剂 ----
        key_catalysts = extra.get("key_catalysts", [])
        catalysts_text = "\n".join(key_catalysts) if key_catalysts else ""

        # ---- 未来情景 ----
        future = extra.get("future_1_4_weeks", {})
        base_case = future.get("base_case", "")
        bull_case = future.get("bull_case", "")
        bear_case = future.get("bear_case", "")

        # ---- 市场反应 ----
        market_price_reaction = extra.get("market_price_reaction", "")
        market_mispricing = extra.get("market_mispricing", "")

        parts.append(f"""
        <hr>
        <h3>{i}. {r["title"]} - MEI {score:.0f}</h3>
        <p><b>类型：</b>{r["category"]} / {r["event_type"]}</p>
        <p><b>评分：</b>Novelty {novelty:.0f};
        Impact {impact:.0f};
        Transmission {trans:.0f};
        Expectation Gap {gap:.0f};
        Sensitivity {sens:.0f}</p>
        <p><b>{direction_emoji} 方向：</b>{direction_label}</p>
        <p><b>📌 预期差：</b>{exp_gap_label} | {exp_gap_detail}</p>
        <p><b>📌 为什么重要：</b>{r["rationale"]}</p>
        """)

        # ---- A股映射（从 affected_assets 解析） ----
        if a_share_name and a_share_ticker:
            parts.append(f"""
            <p><b>🇨🇳 核心A股标的：</b>
            <br><b>{a_share_ticker}</b> {a_share_name} 
            <br>关联度：{a_share_directness}
            <br>逻辑：{a_share_logic}</p>
            """)

        # ---- 美股参考 ----
        if us_reference:
            us_lines = []
            for ref in us_reference:
                if isinstance(ref, dict):
                    ticker = ref.get("ticker", "")
                    company = ref.get("company", "")
                    logic = ref.get("logic", "")
                    us_lines.append(f"<b>{ticker}</b> ({company}): {logic}")
                else:
                    us_lines.append(str(ref))
            parts.append(f"<p><b>🇺🇸 美股参考：</b><br>{'<br>'.join(us_lines)}</p>")

        # ---- 产业链逻辑 ----
        if r.get("industry_chain_logic"):
            parts.append(f"<p><b>🔗 产业链逻辑：</b>{r.get('industry_chain_logic')}</p>")

        # ---- 市场反应 ----
        if market_price_reaction:
            parts.append(f"<p><b>📊 市场反应：</b>{market_price_reaction}</p>")
        if market_mispricing:
            parts.append(f"<p><b>🎯 市场错误定价：</b>{market_mispricing}</p>")

        # ---- 未来情景 ----
        if any([base_case, bull_case, bear_case]):
            parts.append(f"""
            <p><b>🔮 未来1-4周情景：</b>
            <br><b>基准：</b>{base_case}
            <br><b>乐观：</b>{bull_case}
            <br><b>悲观：</b>{bear_case}</p>
            """)

        # ---- 催化剂 ----
        if catalysts_text:
            parts.append(f"<p><b>⏰ 关键催化剂：</b><br>{catalysts_text}</p>")

        # ---- 风险 ----
        parts.append(f"""
        <p><b>⚠️ 风险：</b>{r["risks"]}</p>
        <p><a href="{r["url"]}">查看原文</a></p>
        """)

    parts.append("</body></html>")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Global Market Event Radar | {len(rows)} events"
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    msg.attach(MIMEText("\n".join(parts), "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(MAIL_FROM, [MAIL_TO], msg.as_string())
    print(f"[MAIL] sent {len(rows)} events")


if __name__ == "__main__":
    send_email()
