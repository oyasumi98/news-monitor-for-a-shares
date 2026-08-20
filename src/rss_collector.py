import hashlib
from datetime import datetime, timezone
import feedparser
from .db import init_db, insert_rss

FEEDS = [
    ("Reuters World", "https://feeds.reuters.com/reuters/worldNews"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
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
