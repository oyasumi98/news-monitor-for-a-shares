import hashlib
from datetime import datetime, timezone
import feedparser
from .db import init_db, insert_rss

FEEDS = [
    # ===== 你原有的源 =====
    ("Reuters World", "https://feeds.reuters.com/reuters/worldNews"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("FT Home", "https://www.ft.com/rss/home"),
    ("CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss"),
    ("Yahoo Finance", "https://finance.yahoo.com/rss/topstories"),

    # ===== 新增：彭博财富（更聚焦投资与财富管理） =====
    ("Bloomberg Wealth", "https://feeds.bloomberg.com/wealth/news.rss"),

    # ===== 新增：福布斯投资（投资策略与个人理财） =====
    ("Forbes Investing", "https://www.forbes.com/investing/feed/"),

    # ===== 新增：Investopedia（财经教育与市场分析） =====
    ("Investopedia News", "https://www.investopedia.com/rss/news"),

    # ===== 新增：BBC 商业新闻（英国广播公司） =====
    ("BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml"),

    # ===== 新增：路透社市场新闻（更聚焦市场动态） =====
    ("Reuters Markets", "https://feeds.reuters.com/reuters/MarketsNews"),

    # ===== 国内财经（通过 RSSHub 中转） =====
    # 注意：RSSHub 是第三方服务，稳定性依赖其公共服务器
    ("华尔街见闻", "https://rsshub.app/wallstreetcn/global"),
    ("财新网", "https://rsshub.app/caixin/latest"),
]
def guid_for(source, title, url):
    return hashlib.sha256(f"{source}|{title}|{url}".encode()).hexdigest()

def collect():
    init_db()
    total = 0
    for source, feed_url in FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            title = getattr(entry, "title", "").strip()
            url = getattr(entry, "link", "").strip()
            summary = getattr(entry, "summary", "").strip()
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            guid = getattr(entry, "id", "") or guid_for(source, title, url)
            insert_rss({
                "guid": guid, "published": published, "source": source,
                "title": title, "url": url, "summary": summary,
                "content": summary,
                "collected_at": datetime.now(timezone.utc).isoformat()
            })
            total += 1
    print(f"[RSS] processed={total}")

if __name__ == "__main__":
    collect()
