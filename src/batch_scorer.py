import sqlite3
import json
import requests
from datetime import datetime, timedelta, timezone
from .config import DB_PATH, BATCH_LIMIT, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, GEMINI_API_KEY, GEMINI_MODEL
from .db import init_db
from .llm_prompt import make_batch_prompt
def run_batch(market_text=None, limit=None):
    """
    批量评分：把所有新闻发给LLM，让LLM聚类去重
    
    Args:
        market_text: 可选，由外部传入的市场数据文本，避免重复抓取
        limit: 可选，处理新闻数量上限
    """
    print("[BATCH] ===== 进入 run_batch 函数 =====")
    
if limit is None:
        limit = config.BATCH_LIMIT  # 加上 config.
    print(f"[BATCH] 本次处理上限: {limit} 条")
    
    # 1. 获取未评分的新闻
    items = get_unscored_news(limit)
    if not items:
        print("[BATCH] 没有未评分的新闻")
        return
    
    print(f"[BATCH] 获取到 {len(items)} 条未评分新闻")
    
    # 2. 获取市场数据（如果外部没有传入，则自行获取）
    if market_text is None:
        print("[BATCH] 尝试获取市场数据...")
        try:
            from .market_data import fetch_all_market_data, format_market_data_for_prompt
            market_data_dict = fetch_all_market_data()
            market_text = format_market_data_for_prompt(market_data_dict)
        except Exception as e:
            print(f"[BATCH] 获取市场数据失败: {e}")
            market_text = "unknown"
    else:
        print("[BATCH] 使用外部传入的市场数据")
    
    # 3. 构建批量提示词
    current_time = datetime.now(timezone.utc).isoformat()
    prompt = make_batch_prompt(items, current_time, market_text)
    print(f"[BATCH] 提示词构建完成，长度: {len(prompt)} 字符")
    
    # 4. 调用LLM
    try:
        if DEEPSEEK_API_KEY:
            raw = call_deepseek_batch(prompt)
            model = "deepseek-batch"
            print("[BATCH] DeepSeek 调用成功")
        elif GEMINI_API_KEY:
            raw = call_gemini_batch(prompt)
            model = "gemini-batch"
            print("[BATCH] Gemini 调用成功")
        else:
            raise RuntimeError("未配置API Key")
    except Exception as e:
        print(f"[BATCH] LLM调用失败: {e}")
        return
    
    # 5. 解析JSON
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    print(f"[BATCH] LLM原始返回长度: {len(raw)} 字符")
    print(f"[BATCH] 返回内容预览: {raw[:200]}...")
    
    try:
        events = json.loads(raw)
        if not isinstance(events, list):
            events = [events]
    except json.JSONDecodeError as e:
        print(f"[BATCH] JSON解析失败: {e}")
        print(f"[BATCH] 原始返回: {raw[:500]}...")
        return
    
    # 6. 保存结果
    print(f"[BATCH] LLM返回 {len(events)} 个聚类事件")
    
    saved_count = 0
    for event in events:
        # 为缺失字段补默认值
        event = fill_defaults(event)
        # 保存到数据库
        success = insert_batch_event(event, items)
        if success:
            saved_count += 1
            score = event.get("event_score", 0)
            summary = event.get("news_summary", "")[:50]
            print(f"[BATCH] {score:.0f} | {summary}")
        else:
            print(f"[BATCH] 跳过: {event.get('news_summary', '')[:30]} (无法匹配新闻)")
    
    print(f"[BATCH] 完成，成功保存 {saved_count}/{len(events)} 个事件")
