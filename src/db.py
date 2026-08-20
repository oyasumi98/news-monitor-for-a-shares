import sqlite3
from .config import DB_PATH

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS rss_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guid TEXT UNIQUE, published TEXT, source TEXT NOT NULL,
        title TEXT NOT NULL, url TEXT, summary TEXT, content TEXT,
        collected_at TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS event_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rss_item_id INTEGER UNIQUE, category TEXT, event_type TEXT,
        novelty REAL, economic_impact REAL, transmission REAL,
        expectation_gap REAL, market_sensitivity REAL, event_score REAL,
        direction TEXT, affected_assets TEXT, affected_industries TEXT,
        rationale TEXT, second_order_effects TEXT, risks TEXT,
        model TEXT, scored_at TEXT NOT NULL,
        FOREIGN KEY(rss_item_id) REFERENCES rss_items(id))""")
    con.commit()
    con.close()

def insert_rss(item):
    con = connect()
    con.execute("""INSERT OR IGNORE INTO rss_items
        (guid,published,source,title,url,summary,content,collected_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        tuple(item[k] for k in ("guid","published","source","title","url","summary","content","collected_at")))
    con.commit()
    row = con.execute("SELECT * FROM rss_items WHERE guid=?", (item["guid"],)).fetchone()
    con.close()
    return row

def insert_score(item_id, score):
    con = connect()
    con.execute("""INSERT OR REPLACE INTO event_scores
        (rss_item_id,category,event_type,novelty,economic_impact,transmission,
         expectation_gap,market_sensitivity,event_score,direction,affected_assets,
         affected_industries,rationale,second_order_effects,risks,model,scored_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (item_id, score["category"], score["event_type"], score["novelty"],
         score["economic_impact"], score["transmission"], score["expectation_gap"],
         score["market_sensitivity"], score["event_score"], score["direction"],
         score["affected_assets"], score["affected_industries"], score["rationale"],
         score["second_order_effects"], score["risks"], score["model"], score["scored_at"]))
    con.commit()
    con.close()

def get_recent_scored(min_score, limit):
    con = connect()
    rows = con.execute("""SELECT r.*, e.* FROM rss_items r JOIN event_scores e
        ON r.id=e.rss_item_id WHERE e.event_score>=?
        ORDER BY e.event_score DESC, r.published DESC LIMIT ?""",
        (min_score, limit)).fetchall()
    con.close()
    return rows
