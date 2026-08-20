from .rss_collector import collect
from .scorer import run as score_run
from .email_sender import send_email
from .db import init_db
from .market_data import fetch_all_market_data, format_market_data_for_prompt
def main():
    init_db()
    collect()
    score_run(limit=100)
    send_email()
    # ... 原有的RSS采集和评分逻辑 ...
    
    # 获取市场数据
    market_data = fetch_all_market_data()
    market_text = format_market_data_for_prompt(market_data)
    
    # 可以将 market_text 注入到 LLM 提示词中
    # 例如：在 make_user_prompt 中增加市场快照信息
if __name__ == "__main__":
    main()
