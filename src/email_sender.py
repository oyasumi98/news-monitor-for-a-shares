import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from .config import *
from .db import get_recent_scored
import json

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

        # ---- 解析强关联股票 ----
        us_stocks = []
        a_stocks = []
        try:
            us_raw = r.get("strong_linked_us_stocks", "[]")
            if isinstance(us_raw, str):
                us_stocks = json.loads(us_raw) if us_raw else []
            else:
                us_stocks = us_raw if us_raw else []
        except:
            us_stocks = []

        try:
            a_raw = r.get("strong_linked_a_stocks", "[]")
            if isinstance(a_raw, str):
                a_stocks = json.loads(a_raw) if a_raw else []
            else:
                a_stocks = a_raw if a_raw else []
        except:
            a_stocks = []

        # ---- 解析 price_anomaly ----
        price_anomaly = {}
        try:
            pa_raw = r.get("price_anomaly", "{}")
            if isinstance(pa_raw, str):
                price_anomaly = json.loads(pa_raw) if pa_raw else {}
            else:
                price_anomaly = pa_raw if pa_raw else {}
        except:
            price_anomaly = {}

        parts.append(f"""
        <hr>
        <h3>{i}. {r["title"]} - MEI {score:.0f}</h3>
        <p><b>类型：</b>{r["category"]} / {r["event_type"]}</p>
        <p><b>评分：</b>Novelty {novelty:.0f};
        Impact {impact:.0f};
        Transmission {trans:.0f};
        Expectation Gap {gap:.0f};
        Sensitivity {sens:.0f}</p>
        <p><b>📌 发生了什么：</b>{r["news_summary"]}</p>
        <p><b>🔄 边际变化：</b>{r["marginal_change"]}</p>
        <p><b>为什么重要：</b>{r["rationale"]}</p>
        <p><b>产业链逻辑：</b>{r["industry_chain_logic"]}</p>
        """)

        # 强关联美股
        if us_stocks:
            stock_lines = []
            for s in us_stocks:
                ticker = s.get("ticker", "")
                company = s.get("company", "")
                rel = s.get("relationship", "")
                logic = s.get("logic", "")
                stock_lines.append(f"<b>{ticker}</b> ({company}) - {rel}: {logic}")
            parts.append(f"<p><b>🇺🇸 强关联美股：</b><br>{'<br>'.join(stock_lines)}</p>")

        # 强关联A股
        if a_stocks:
            stock_lines = []
            for s in a_stocks:
                ticker = s.get("ticker", "")
                company = s.get("company", "")
                rel = s.get("relationship", "")
                logic = s.get("logic", "")
                stock_lines.append(f"<b>{ticker}</b> ({company}) - {rel}: {logic}")
            parts.append(f"<p><b>🇨🇳 强关联A股：</b><br>{'<br>'.join(stock_lines)}</p>")

        # 价格异常
        if price_anomaly and price_anomaly.get("stock"):
            parts.append(f"""
            <p><b>📊 价格异常：</b>{price_anomaly.get('stock')} 
            涨跌幅 {price_anomaly.get('change_pct', 0):.1f}% 
            | 疑似原因：{price_anomaly.get('suspected_reason', '')}
            | 置信度：{price_anomaly.get('confidence', 'unknown')}</p>
            """)

        # 催化剂
        if r.get("validation_catalyst"):
            parts.append(f"<p><b>⏰ 验证催化剂：</b>{r['validation_catalyst']}</p>")

        parts.append(f"""
        <p><b>风险：</b>{r["risks"]}</p>
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
