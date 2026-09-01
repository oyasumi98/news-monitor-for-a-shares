import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from .config import *
from .db import get_recent_scored


def send_email():
    rows = get_recent_scored(min_score=0, limit=100)
    if not rows:
        print("[MAIL] 没有评分事件")
        return

    rows.sort(key=lambda x: float(x.get("event_score", 0)), reverse=True)

    category_best = {}
    for r in rows:
        cat = r.get("category", "other")
        if cat not in category_best:
            category_best[cat] = r
        else:
            if float(r.get("event_score", 0)) > float(category_best[cat].get("event_score", 0)):
                category_best[cat] = r

    best_events = sorted(category_best.values(), key=lambda x: float(x.get("event_score", 0)), reverse=True)[:20]

    if not best_events:
        print("[MAIL] 没有符合条件的事件")
        return

    parts = ["<html><body><h2>Global Market Event Radar - Top 20 (类别去重)</h2>"]

    for i, row in enumerate(best_events, 1):
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

        extra = {}
        try:
            affected_raw = r.get("affected_assets", "{}")
            if isinstance(affected_raw, str):
                extra = json.loads(affected_raw) if affected_raw else {}
            else:
                extra = affected_raw if affected_raw else {}
        except:
            pass

        a_share = extra.get("a_share", {})
        a_name = a_share.get("name", "")
        a_ticker = a_share.get("ticker", "")
        a_logic = a_share.get("logic", "")
        a_directness = a_share.get("directness", "")

        us_ref = extra.get("us_reference", [])
        exp_gap_detail = extra.get("expectation_gap_detail", "")
        catalysts = extra.get("key_catalysts", [])
        catalyst_text = "\n".join(catalysts) if catalysts else ""
        industry_chain = extra.get("industry_chain_logic", "") or r.get("industry_chain_logic", "")

        direction = r.get("direction", "unknown")
        dir_emoji = {"positive": "🟢", "negative": "🔴", "mixed": "🟡", "unknown": "⚪"}.get(direction, "⚪")
        dir_label = {"positive": "利好", "negative": "利空", "mixed": "混合", "unknown": "未知"}.get(direction, "未知")

        exp_gap = r.get("expectation_gap", "unknown")
        gap_label = {"high": "高", "medium": "中", "low": "低", "unknown": "未知"}.get(exp_gap, "未知")

        parts.append(f"""
        <hr>
        <h3>{i}. {r["title"]} - MEI {score:.0f}</h3>
        <p><b>类型：</b>{r["category"]} / {r["event_type"]}</p>
        <p><b>评分：</b>Novelty {novelty:.0f}; Impact {impact:.0f}; Transmission {trans:.0f}; Expectation Gap {gap:.0f}; Sensitivity {sens:.0f}</p>
        <p><b>{dir_emoji} 方向：</b>{dir_label}</p>
        <p><b>📌 预期差：</b>{gap_label} | {exp_gap_detail}</p>
        <p><b>📌 发生了什么：</b>{r.get("news_summary", "") or r.get("rationale", "")}</p>
        """)

        if a_name and a_ticker:
            parts.append(f"""
            <p><b>🇨🇳 核心A股标的：</b>
            <br><b>{a_ticker}</b> {a_name} 
            <br>关联度：{a_directness}
            <br>逻辑：{a_logic}</p>
            """)

        if industry_chain:
            parts.append(f"<p><b>🔗 产业链逻辑：</b>{industry_chain}</p>")

        if catalyst_text:
            parts.append(f"<p><b>⏰ 催化剂：</b><br>{catalyst_text}</p>")

        if r.get("risks"):
            parts.append(f"<p><b>⚠️ 风险：</b>{r['risks']}</p>")

        parts.append(f'<p><a href="{r["url"]}">查看原文</a></p>')

    parts.append("</body></html>")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Global Market Event Radar | 精选 {len(best_events)} 个事件"
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    msg.attach(MIMEText("\n".join(parts), "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(MAIL_FROM, [MAIL_TO], msg.as_string())
    print(f"[MAIL] 发送 {len(best_events)} 个事件")


if __name__ == "__main__":
    send_email()
