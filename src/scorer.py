import sqlite3
from .config import DB_PATH
from .db import init_db, insert_score
from .llm_client import score_item

def run(limit=100):
    init_db()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("""SELECT r.* FROM rss_items r
        LEFT JOIN event_scores e ON r.id=e.rss_item_id
        WHERE e.id IS NULL ORDER BY r.id DESC LIMIT ?""", (limit,)).fetchall()
    con.close()

    # ----- 硬去重：基于标题前30字符 -----
    seen = {}
    deduped = []
    for row in rows:
        key = row["title"][:30].strip()
        if key in seen:
            print(f"[去重] 跳过相似标题: {row['title']}")
            continue
        seen[key] = True
        deduped.append(row)
    rows = deduped
    print(f"[去重] 去重后剩余 {len(rows)} 条")
    # ----- 硬去重结束 -----

    for row in rows:
        item = dict(row)
        try:
            s = score_item(item)
            insert_score(item["id"], s)
            print(f"[LLM] {float(s['event_score']):.0f} | {item['title']}")
        except Exception as exc:
            print(f"[ERROR] {item['title']} -> {exc}")

if __name__ == "__main__":
    run()
