from .rss_collector import collect
from .email_sender import send_email
from .db import init_db
from .market_data import fetch_all_market_data, format_market_data_for_prompt
from .batch_scorer import run_batch

def main():
    init_db()
    
    # 1. RSS采集
    print("[MAIN] 开始采集RSS...")
    collect()
    
    # 2. 获取市场数据（放在批量评分之前，且失败不影响主流程）
    print("[MAIN] 获取市场数据...")
    try:
        market_data = fetch_all_market_data()
        market_text = format_market_data_for_prompt(market_data)
        print("[MAIN] 市场数据获取成功")
    except Exception as e:
        print(f"[MAIN] 市场数据获取失败，继续执行: {e}")
        market_text = "unknown"
    
    # 3. 批量评分（聚类去重）
    # run_batch 内部会调用 make_batch_prompt，并把 market_text 传进去
    print("[MAIN] 开始批量评分...")
    run_batch(market_text=market_text)  # 需要修改 batch_scorer 支持 market_text 参数
    
    # 4. 发送邮件
    send_email()

if __name__ == "__main__":
    main()
