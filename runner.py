"""
runner.py - Main scheduler loop.

Schedule:
  - Every 2-4 hours: fetch RSS, filter posts, generate comments, save to queue.
  - Every 30 minutes: check approved queue, post via Playwright, log results.

Run with:
  python runner.py
"""

import os
import random
import time
import logging
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("runner")

TARGET_SUBREDDITS = [
    s.strip()
    for s in os.getenv(
        "TARGET_SUBREDDITS", "fitness,loseit,nutrition,Entrepreneur,startups"
    ).split(",")
    if s.strip()
]

# Interval ranges (seconds)
SCRAPE_INTERVAL_MIN = int(os.getenv("SCRAPE_INTERVAL_MIN", str(2 * 3600)))   # 2 h
SCRAPE_INTERVAL_MAX = int(os.getenv("SCRAPE_INTERVAL_MAX", str(4 * 3600)))   # 4 h
POST_CHECK_INTERVAL = int(os.getenv("POST_CHECK_INTERVAL", str(30 * 60)))    # 30 min


# ---------------------------------------------------------------------------
# Core task functions
# ---------------------------------------------------------------------------


def run_scrape_and_generate() -> None:
    """Fetch new posts, filter them, generate comments, and save to the queue."""
    from scraper import fetch_all_subreddits
    from filter import filter_posts, save_post
    from llm import generate_comment

    logger.info("=== Scrape & Generate run started ===")

    posts = fetch_all_subreddits(TARGET_SUBREDDITS)
    logger.info("Total posts fetched: %d", len(posts))

    relevant = filter_posts(posts)
    logger.info("Relevant new posts: %d", len(relevant))

    for post in relevant:
        logger.info(
            "Generating comment for: [%s] %s", post["subreddit"], post["title"][:60]
        )
        comment = generate_comment(post["subreddit"], post["title"])
        row_id = save_post(post, comment)
        if row_id is not None:
            logger.info("Saved to queue with id=%d", row_id)
        else:
            logger.debug("Post already in queue, skipped.")

    logger.info("=== Scrape & Generate run finished ===")


def run_post_approved() -> None:
    """Post all approved comments, respecting the daily rate limit."""
    from poster import run_posting_queue

    logger.info("=== Posting run started ===")
    run_posting_queue()
    logger.info("=== Posting run finished ===")


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------


def main() -> None:
    logger.info("Reddit Ad Automation runner starting up.")
    logger.info("Target subreddits: %s", ", ".join(TARGET_SUBREDDITS))

    # Initialise the database on first run
    from filter import init_db
    init_db()

    next_scrape = time.monotonic()          # run immediately on first iteration
    next_post_check = time.monotonic()      # run immediately on first iteration

    while True:
        now = time.monotonic()

        if now >= next_scrape:
            try:
                run_scrape_and_generate()
            except Exception as exc:
                logger.error("Scrape/generate cycle failed: %s", exc)

            interval = random.randint(SCRAPE_INTERVAL_MIN, SCRAPE_INTERVAL_MAX)
            next_scrape = time.monotonic() + interval
            logger.info(
                "Next scrape in %d min (≈ %s)",
                interval // 60,
                datetime.fromtimestamp(time.time() + interval).strftime("%H:%M"),
            )

        if now >= next_post_check:
            try:
                run_post_approved()
            except Exception as exc:
                logger.error("Posting cycle failed: %s", exc)

            next_post_check = time.monotonic() + POST_CHECK_INTERVAL
            logger.info(
                "Next posting check in %d min",
                POST_CHECK_INTERVAL // 60,
            )

        # Sleep until the next event is due
        sleep_secs = min(next_scrape - time.monotonic(),
                         next_post_check - time.monotonic())
        sleep_secs = max(sleep_secs, 1)
        logger.debug("Sleeping for %.0f seconds...", sleep_secs)
        time.sleep(sleep_secs)


if __name__ == "__main__":
    main()
