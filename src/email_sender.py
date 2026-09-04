import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from .config import *
from .db import get_recent_scored


def select_top_pick(events):
    """选出当日最推荐的股票，综合考虑评分、逻辑链和直接受益程度"""
    best = None
    best_score = -1
    
    for event in events:
        extra = {}
        try:
            affected_raw = event.get("affected_assets", "{}")
            if isinstance(affected_raw, str):
                extra = json.loads(affected_raw) if affected_raw else {}
            else:
                extra = affected_raw if affected_raw else {}
        except:
            pass
        
        a_share = extra.get("a_share", {})
        if not a_share.get("name"):
            continue
        
        # 综合评分：事件评分 + 逻辑链完整度加分 + 直接受益加分
        score = float(event.get("event_score", 0))
        
        # 逻辑链越长越加分（至少3步）
        logic_chain = extra.get("logic_chain", "")
        if logic_chain:
            step_count = logic_chain.count("→") + 1
            if step_count >= 3:
                score += 15
            elif step_count >= 2:
                score += 8
        
        # 直接受益加分
        directness = a_share.get("directness", "INDIRECT")
        if directness == "DIRECT":
            score += 10
        elif directness == "INDIRECT":
            score += 5
        
        if score > best_score:
            best_score = score
            best = {
                "name": a_share.get("name"),
                "ticker": a_share.get("ticker"),
                "logic": a_share.get("logic", ""),
                "logic_chain": extra.get("logic_chain", ""),
                "event_score": event.get("event_score", 0),
                "title": event.get("title", ""),
                "direction": event.get("direction", "unknown"),
                "direction_reason": extra.get("direction_reason", "")
            }
    
    return best


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

    parts = ["<html><body><h2>🌍 全球市场事件雷达 - 今日精选</h2>"]

    # ---- 推荐板块 ----
    top_pick = select_top_pick(best_events)
    if top_pick:
        direction_text = "🟢 利好" if top_pick['direction'] == 'positive' else "🔴 利空" if top_pick['direction'] == 'negative' else "🟡 中性"
        parts.append(f"""
        <div style="background: #f0f7ff; border: 2px solid #1890ff; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
        <h3>⭐ 今日最推荐：{top_pick['name']}（{top_pick['ticker']}）</h3>
        <p><b>驱动事件：</b>{top_pick['title']}</p>
        <p><b>方向：</b>{direction_text}</p>
        <p><b>方向理由：</b>{top_pick['direction_reason'] or "基于事件基本面判断"}</p>
        <p><b>逻辑链：</b>{top_pick['logic_chain'] or top_pick['logic']}</p>
        <p><b>事件评分：</b>{top_pick['event_score']:.0f}</p>
        </div>
        """)

    # ---- 事件列表 ----
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

        # ---- 新增字段 ----
        logic_chain = extra.get("logic_chain", "")
        direction_reason = extra.get("direction_reason", "")
        exp_gap_detail = extra.get("expectation_gap_detail", "")
        industry_chain = extra.get("industry_chain_logic", "") or r.get("industry_chain_logic", "")

        catalysts = extra.get("key_catalysts", [])
        catalyst_text = "\n".join(catalysts) if catalysts else ""

        direction = r.get("direction", "unknown")
        dir_emoji = {"positive": "🟢", "negative": "🔴", "mixed": "🟡", "unknown": "⚪"}.get(direction, "⚪")
        dir_label = {"positive": "利好", "negative": "利空", "mixed": "混合", "unknown": "未知"}.get(direction, "未知")

        exp_gap = r.get("expectation_gap", "unknown")
        gap_label = {"high": "高", "medium": "中", "low": "低", "unknown": "未知"}.get(exp_gap, "未知")

        parts.append(f"""
        <hr>
        <h3>{i}. {r["title"]}</h3>
        <p><b>类型：</b>{r["category"]} / {r["event_type"]}</p>
        <p><b>评分：</b>新颖性 {novelty:.0f}；影响 {impact:.0f}；传导 {trans:.0f}；预期差 {gap:.0f}；敏感性 {sens:.0f}</p>
        <p><b>{dir_emoji} 方向：</b>{dir_label}</p>
        """)

        # 方向理由（如果有）
        if direction_reason:
            parts.append(f"<p><b>📊 方向理由：</b>{direction_reason}</p>")

        parts.append(f"<p><b>📌 核心事件：</b>{r.get('news_summary', '') or r.get('rationale', '')}</p>")

        # 逻辑链（优先展示完整逻辑链）
        if logic_chain:
            parts.append(f"<p><b>🔗 逻辑链：</b>{logic_chain}</p>")
        elif industry_chain:
            parts.append(f"<p><b>🔗 产业链传导：</b>{industry_chain}</p>")

        if a_name and a_ticker:
            parts.append(f"""
            <p><b>🇨🇳 核心A股标的：</b>
            <br><b>{a_ticker}</b> {a_name} 
            <br>关联度：{a_directness}
            <br>逻辑：{a_logic}</p>
            """)

        if exp_gap_detail:
            parts.append(f"<p><b>📊 预期差：</b>{gap_label} | {exp_gap_detail}</p>")

        if catalyst_text:
            parts.append(f"<p><b>⏰ 催化剂：</b><br>{catalyst_text}</p>")

        if r.get("risks"):
            parts.append(f"<p><b>⚠️ 风险：</b>{r['risks']}</p>")

        parts.append(f'<p><a href="{r["url"]}">📎 查看原文</a></p>')

    parts.append("</body></html>")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🌍 全球市场事件雷达 | 精选 {len(best_events)} 个事件"
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    msg.attach(MIMEText("\n".join(parts), "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(MAIL_FROM, [MAIL_TO], msg.as_string())
    print(f"[MAIL] 发送 {len(best_events)} 个事件")


if __name__ == "__main__":
    send_email()
