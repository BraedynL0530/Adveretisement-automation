"""
poster.py - Post approved comments to Reddit via Playwright browser automation.
Saves auth session to auth.json to avoid repeated logins.
"""

import os
import random
import time
import logging
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = "queue.db"
AUTH_FILE = "auth.json"

REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD", "")
POST_DELAY_MIN = int(os.getenv("POST_DELAY_MIN", "30"))
POST_DELAY_MAX = int(os.getenv("POST_DELAY_MAX", "120"))
POSTS_PER_DAY = int(os.getenv("POSTS_PER_DAY", "3"))


def _update_status(row_id: int, status: str, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE queue SET status = ? WHERE id = ?", (status, row_id)
        )
        conn.commit()


def _count_posted_today(db_path: str = DB_PATH) -> int:
    """Count posts made today to enforce the daily rate limit."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM queue
            WHERE status = 'posted'
              AND date(created_at) = date('now')
            """
        ).fetchone()
    return row[0] if row else 0


def get_approved_items(db_path: str = DB_PATH):
    """Return all queue rows with status='approved'."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM queue WHERE status = 'approved' ORDER BY created_at ASC"
        ).fetchall()


def _login(page, context) -> bool:
    """Log in to Reddit. Returns True on success."""
    if not REDDIT_USERNAME or not REDDIT_PASSWORD:
        logger.error("REDDIT_USERNAME / REDDIT_PASSWORD not set in .env")
        return False

    try:
        page.goto("https://www.reddit.com/login/", wait_until="domcontentloaded")
        page.fill('input[name="username"]', REDDIT_USERNAME)
        page.fill('input[name="password"]', REDDIT_PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_url("https://www.reddit.com/**", timeout=15000)

        # Save auth state for future runs
        context.storage_state(path=AUTH_FILE)
        logger.info("Logged in and saved session to %s", AUTH_FILE)
        return True

    except Exception as exc:
        logger.error("Login failed: %s", exc)
        return False


def post_comment(row_id: int, post_url: str, comment_text: str) -> bool:
    """
    Open the Reddit post, find the comment box, type the comment, and submit.
    Returns True if successful.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error("playwright not installed. Run: pip install playwright")
        return False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        # Reuse saved auth session if it exists
        context_kwargs = {}
        if Path(AUTH_FILE).exists():
            context_kwargs["storage_state"] = AUTH_FILE

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        # Check if we're already logged in, otherwise log in
        page.goto("https://www.reddit.com/", wait_until="domcontentloaded")
        if page.url.startswith("https://www.reddit.com/login") or not page.query_selector('[data-testid="user-menu"]'):
            if not _login(page, context):
                browser.close()
                return False

        try:
            page.goto(post_url, wait_until="domcontentloaded")

            # Click the comment box (Reddit's new UI)
            comment_box = page.locator(
                '[data-testid="comment-textarea"], '
                'div[data-click-id="text"] textarea, '
                '#CommentSort--SortPicker ~ * textarea, '
                'div.commentarea textarea, '
                'shreddit-composer textarea'
            ).first
            comment_box.wait_for(timeout=10000)
            comment_box.click()
            comment_box.fill(comment_text)

            # Random short pause before submitting (human-like)
            time.sleep(random.uniform(1.5, 3.5))

            # Click submit button
            submit_btn = page.locator(
                'button[type="submit"]:has-text("Comment"), '
                'button:has-text("Save"), '
                'button[data-click-id="text"]'
            ).first
            submit_btn.click()

            # Wait briefly to confirm the comment appeared
            page.wait_for_timeout(4000)

            logger.info("Posted comment to %s", post_url)
            _update_status(row_id, "posted")
            browser.close()
            return True

        except PWTimeout:
            logger.error("Timeout while posting to %s", post_url)
            _update_status(row_id, "failed")
        except Exception as exc:
            logger.error("Error posting to %s: %s", post_url, exc)
            _update_status(row_id, "failed")

        browser.close()
        return False


def run_posting_queue(db_path: str = DB_PATH) -> None:
    """Process all approved items in the queue, respecting the daily rate limit."""
    posted_today = _count_posted_today(db_path)
    if posted_today >= POSTS_PER_DAY:
        logger.info(
            "Daily limit reached (%d/%d). Skipping posting run.",
            posted_today,
            POSTS_PER_DAY,
        )
        return

    approved = get_approved_items(db_path)
    if not approved:
        logger.info("No approved items to post.")
        return

    for item in approved:
        if posted_today >= POSTS_PER_DAY:
            logger.info("Daily limit reached mid-run. Stopping.")
            break

        logger.info(
            "Posting item #%d: %s", item["id"], item["post_title"][:60]
        )
        success = post_comment(item["id"], item["post_url"], item["generated_comment"])

        if success:
            posted_today += 1

        # Random delay between posts
        delay = random.uniform(POST_DELAY_MIN, POST_DELAY_MAX)
        logger.info("Waiting %.0f seconds before next post...", delay)
        time.sleep(delay)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_posting_queue()
