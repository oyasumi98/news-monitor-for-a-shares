import hashlib
from datetime import datetime, timezone
import feedparser
from .db import init_db, insert_rss

FEEDS = [
    # 路透社
    ("Reuters World", "https://feeds.reuters.com/reuters/worldNews"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    
    # 新增：道琼斯/华尔街日报
    ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    
    # 新增：金融时报
    ("FT Home", "https://www.ft.com/rss/home"),
    
    # 新增：CNBC
    ("CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    
    # 新增：彭博（Bloomberg 官方 RSS 可能需要特殊处理，以下地址可尝试）
    ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss"),
    
    # 新增：雅虎财经
    ("Yahoo Finance", "https://finance.yahoo.com/rss/topstories"),
    
    # 如果想加入国内财经（部分可用）
    # ("财新网", "https://rss.caixin.com/roll.xml"),
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
