# Market Event Radar V2

RSS -> SQLite -> DeepSeek/Gemini -> Email 的每日自动运行原型。

## 安装
python -m venv .venv
pip install -r requirements.txt

## 配置
复制 .env.example 为 .env。
DeepSeek/Gemini 二选一。
邮件使用 SMTP 授权码，不要使用邮箱网页登录密码。

## 运行
python -m src.main

## 分步调试
python -m src.rss_collector
python -m src.scorer
python -m src.email_sender

## Windows自动运行
任务计划程序 -> 每天 -> 例如18:30 -> Python -> 参数：
-m src.main
起始位置：项目根目录

## Linux/云服务器
cron：
30 10 * * 1-5 cd /path/market_event_radar_v2 && /path/.venv/bin/python -m src.main >> radar.log 2>&1

## 后续升级
增加官方政策源、SEC、公司IR、科技媒体、财报、市场行情；
做新闻去重/事件聚类、市场预期、资产映射、T+1/T+5/T+20回测和Walk-forward训练。
