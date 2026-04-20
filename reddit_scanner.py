"""
reddit_scanner.py - Scan Reddit subreddits for relevant posts/comments.

Uses the Reddit JSON API (no auth required).
Calls local Ollama (Gemma 3) to check relevance.
On match: triggers an email notification with link + context.
Stores seen URLs in SQLite to avoid duplicate alerts.
"""

import os
import sqlite3
import logging
import time
from typing import List, Dict, Optional
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
TARGET_SUBREDDITS = [
    s.strip()
    for s in os.getenv(
        "TARGET_SUBREDDITS", "fitness,loseit,nutrition,Entrepreneur,startups"
    ).split(",")
    if s.strip()
]
DB_PATH = os.getenv("DB_PATH", "queue.db")
NUTRIFITNESS_URL = os.getenv("NUTRIFITNESS_URL", "nut-ri-fitness.app")

# Max age of posts to consider (30 days in seconds)
MAX_POST_AGE_SECONDS = 30 * 24 * 3600

REDDIT_JSON_HEADERS = {
    "User-Agent": "NutriFITNESS-Scanner/1.0 (contact via nut-ri-fitness.app)"
}

RELEVANCE_PROMPT = """\
You are a filter bot for a nutrition/fitness SaaS app called Nutrifitness.

Decide if this Reddit post or comment is relevant to ANY of:
- Calorie tracking, macro tracking, food logging
- Fitness app recommendations or complaints
- Nutrition advice, diet tips, healthy eating
- Weight loss or muscle gain questions
- Meal planning or recipe discovery

Post title: {title}
Post body: {body}

Reply with only YES or NO. No explanation.
"""

SUGGESTED_REPLY_PROMPT = """\
You are a friendly Reddit user who uses a calorie-tracking app called Nutrifitness (nut-ri-fitness.app).

A Reddit user posted:
Title: {title}
Body: {body}
Subreddit: r/{subreddit}

Write a short, genuine, helpful reply (2-4 sentences max).
Naturally mention Nutrifitness only if it fits the conversation.
Sound like a real person. No emojis. No hashtags. No marketing language.
"""


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def init_db(db_path: str = DB_PATH) -> None:
    """Create queue tables if they don't exist."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reddit_seen (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                url        TEXT    NOT NULL UNIQUE,
                subreddit  TEXT    NOT NULL,
                title      TEXT    NOT NULL,
                notified   INTEGER NOT NULL DEFAULT 0,
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS video_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url  TEXT    NOT NULL UNIQUE,
                title       TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'pending',
                output_path TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    logger.info("Database initialised at %s", db_path)


def already_seen(url: str, db_path: str = DB_PATH) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM reddit_seen WHERE url = ?", (url,)
        ).fetchone()
    return row is not None


def mark_seen(url: str, subreddit: str, title: str, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO reddit_seen (url, subreddit, title, notified) VALUES (?, ?, ?, 1)",
            (url, subreddit, title),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Reddit JSON fetching
# ---------------------------------------------------------------------------


def _fetch_json(url: str, retries: int = 3, backoff: float = 2.0) -> Optional[dict]:
    for attempt in range(retries):
        try:
            resp = requests.get(
                url,
                headers=REDDIT_JSON_HEADERS,
                timeout=15,
            )
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", backoff * (attempt + 1)))
                logger.warning("Rate limited by Reddit, waiting %.0fs", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("Fetch attempt %d failed: %s", attempt + 1, exc)
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    return None


def fetch_posts(subreddit: str) -> List[Dict]:
    """Fetch recent posts from a subreddit via the JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=50"
    data = _fetch_json(url)
    if not data:
        logger.error("Failed to fetch posts from r/%s", subreddit)
        return []

    posts = []
    now_ts = datetime.now(timezone.utc).timestamp()

    try:
        for child in data["data"]["children"]:
            post = child["data"]
            age = now_ts - post.get("created_utc", 0)
            if age > MAX_POST_AGE_SECONDS:
                continue

            posts.append(
                {
                    "type": "post",
                    "subreddit": subreddit,
                    "title": post.get("title", "").strip(),
                    "body": post.get("selftext", "").strip()[:500],
                    "url": f"https://www.reddit.com{post['permalink']}",
                    "score": post.get("score", 0),
                    "created_utc": post.get("created_utc", 0),
                }
            )
    except (KeyError, TypeError) as exc:
        logger.error("Error parsing posts from r/%s: %s", subreddit, exc)

    logger.info("Fetched %d posts from r/%s", len(posts), subreddit)
    return posts


def fetch_comments(subreddit: str) -> List[Dict]:
    """Fetch recent comments from a subreddit via the JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/comments.json?limit=50"
    data = _fetch_json(url)
    if not data:
        logger.error("Failed to fetch comments from r/%s", subreddit)
        return []

    comments = []
    now_ts = datetime.now(timezone.utc).timestamp()

    try:
        for child in data["data"]["children"]:
            comment = child["data"]
            age = now_ts - comment.get("created_utc", 0)
            if age > MAX_POST_AGE_SECONDS:
                continue

            body = comment.get("body", "").strip()
            if not body or body in ("[deleted]", "[removed]"):
                continue

            link_url = (
                f"https://www.reddit.com{comment['permalink']}"
                if "permalink" in comment
                else ""
            )
            if not link_url:
                continue

            comments.append(
                {
                    "type": "comment",
                    "subreddit": subreddit,
                    "title": comment.get("link_title", "(comment)").strip(),
                    "body": body[:500],
                    "url": link_url,
                    "score": comment.get("score", 0),
                    "created_utc": comment.get("created_utc", 0),
                }
            )
    except (KeyError, TypeError) as exc:
        logger.error("Error parsing comments from r/%s: %s", subreddit, exc)

    logger.info("Fetched %d comments from r/%s", len(comments), subreddit)
    return comments


# ---------------------------------------------------------------------------
# AI relevance check via local Ollama
# ---------------------------------------------------------------------------


def _call_ollama(prompt: str) -> str:
    """Send a prompt to the local Ollama API and return the response text."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to Ollama at %s — is the app running?", OLLAMA_URL)
        return ""
    except Exception as exc:
        logger.error("Ollama error: %s", exc)
        return ""


def is_relevant(item: Dict) -> bool:
    """Ask Ollama whether this post/comment is relevant to Nutrifitness."""
    prompt = RELEVANCE_PROMPT.format(
        title=item.get("title", ""),
        body=item.get("body", ""),
    )
    response = _call_ollama(prompt)
    if not response:
        # Fallback: keyword-based check if Ollama is unavailable
        keywords = [
            "calorie", "calori", "macro", "protein", "track", "log", "diet",
            "fitness", "nutrition", "weight", "lose", "gain", "recipe", "meal",
            "app", "myfitnesspal", "loseit", "food",
        ]
        text = (item.get("title", "") + " " + item.get("body", "")).lower()
        return any(kw in text for kw in keywords)

    return response.strip().upper().startswith("YES")


def generate_suggested_reply(item: Dict) -> str:
    """Ask Ollama for a suggested reply (optional, may be empty)."""
    prompt = SUGGESTED_REPLY_PROMPT.format(
        title=item.get("title", ""),
        body=item.get("body", ""),
        subreddit=item.get("subreddit", ""),
    )
    return _call_ollama(prompt)


# ---------------------------------------------------------------------------
# Main scan function
# ---------------------------------------------------------------------------


def scan_subreddits(
    subreddits: Optional[List[str]] = None,
    db_path: str = DB_PATH,
) -> List[Dict]:
    """
    Scan subreddits for relevant posts/comments.

    Returns a list of relevant items that haven't been notified about yet.
    Each item is also marked as seen in the DB so it won't fire again.
    """
    if subreddits is None:
        subreddits = TARGET_SUBREDDITS

    init_db(db_path)

    matches = []

    for subreddit in subreddits:
        items = fetch_posts(subreddit) + fetch_comments(subreddit)
        # Pause briefly between subreddits to be polite to Reddit
        time.sleep(1)

        for item in items:
            url = item.get("url", "")
            if not url:
                continue
            if already_seen(url, db_path):
                continue

            if is_relevant(item):
                logger.info(
                    "Relevant %s found in r/%s: %s",
                    item["type"],
                    subreddit,
                    item["title"][:80],
                )
                # Generate a suggested reply (best-effort)
                item["suggested_reply"] = generate_suggested_reply(item)
                mark_seen(url, subreddit, item["title"], db_path)
                matches.append(item)
            else:
                # Still mark it seen so we don't re-check every run
                mark_seen(url, subreddit, item["title"], db_path)

    logger.info("Scan complete — %d relevant items found across %d subreddits",
                len(matches), len(subreddits))
    return matches


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    matches = scan_subreddits()
    for m in matches:
        print(f"\n[{m['subreddit']}] {m['type'].upper()}: {m['title']}")
        print(f"  URL: {m['url']}")
        if m.get("suggested_reply"):
            print(f"  Suggested reply: {m['suggested_reply'][:120]}...")
