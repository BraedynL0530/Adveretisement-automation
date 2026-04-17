"""
filter.py - Filter posts for relevance and avoid duplicates.
"""

import sqlite3
import logging
from typing import List, Dict

from scraper import KEYWORDS

logger = logging.getLogger(__name__)

DB_PATH = "queue.db"

EXCLUDE_KEYWORDS = [
    "meme", "shitpost", "rant", "[meta]", "humor", "joke",
]


def init_db(db_path: str = DB_PATH) -> None:
    """Create the SQLite queue table if it doesn't exist."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subreddit   TEXT    NOT NULL,
                post_title  TEXT    NOT NULL,
                post_url    TEXT    NOT NULL UNIQUE,
                generated_comment TEXT,
                status      TEXT    NOT NULL DEFAULT 'pending',
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    logger.info("Database initialised at %s", db_path)


def already_seen(post_url: str, db_path: str = DB_PATH) -> bool:
    """Return True if we have already queued or processed this post URL."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM queue WHERE post_url = ?", (post_url,)
        ).fetchone()
    return row is not None


def is_relevant(title: str) -> bool:
    """Return True when the title matches at least one target keyword
    and none of the exclusion keywords."""
    lower = title.lower()
    has_keyword = any(kw in lower for kw in KEYWORDS)
    has_exclusion = any(ex in lower for ex in EXCLUDE_KEYWORDS)
    return has_keyword and not has_exclusion


def filter_posts(posts: List[Dict], db_path: str = DB_PATH) -> List[Dict]:
    """Return only new, relevant posts that haven't been seen before."""
    init_db(db_path)
    filtered = []
    for post in posts:
        if not is_relevant(post["title"]):
            logger.debug("Skipping (not relevant): %s", post["title"])
            continue
        if already_seen(post["url"], db_path):
            logger.debug("Skipping (duplicate): %s", post["url"])
            continue
        filtered.append(post)
    logger.info(
        "Filtered %d/%d posts as new & relevant", len(filtered), len(posts)
    )
    return filtered


def save_post(post: Dict, comment: str, db_path: str = DB_PATH) -> int | None:
    """Insert a post + generated comment into the queue.

    Returns the new row id on successful insert, or None if the URL already exists.
    """
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO queue
                (subreddit, post_title, post_url, generated_comment, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (post["subreddit"], post["title"], post["url"], comment),
        )
        conn.commit()
        # rowcount is 0 when INSERT OR IGNORE skipped a duplicate
        if cur.rowcount == 0:
            return None
        return cur.lastrowid


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("Database ready.")
