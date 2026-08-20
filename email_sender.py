import smtplib
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
    for i, r in enumerate(rows, 1):
        parts.append(f"""
        <hr>
        <h3>{i}. {r["title"]} - MEI {float(r["event_score"]):.0f}</h3>
        <p><b>类型：</b>{r["category"]} / {r["event_type"]}</p>
        <p><b>评分：</b>Novelty {r["novelty"]:.0f};
        Impact {r["economic_impact"]:.0f};
        Transmission {r["transmission"]:.0f};
        Expectation Gap {r["expectation_gap"]:.0f};
        Sensitivity {r["market_sensitivity"]:.0f}</p>
        <p><b>为什么重要：</b>{r["rationale"]}</p>
        <p><b>二阶/三阶影响：</b>{r["second_order_effects"]}</p>
        <p><b>受影响资产：</b>{r["affected_assets"]}</p>
        <p><b>受影响行业：</b>{r["affected_industries"]}</p>
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
