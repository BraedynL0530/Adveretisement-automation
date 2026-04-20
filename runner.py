"""
runner.py - Main scheduler loop.

Schedule:
  - Every 2 hours:  scan Reddit subreddits, email alerts on relevant matches.
  - Every 12 hours: fetch recipe videos, auto-edit, send desktop notification.

Run with:
  python runner.py
"""

import os
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

# Intervals (seconds)
REDDIT_SCAN_INTERVAL = int(os.getenv("REDDIT_SCAN_INTERVAL", str(2 * 3600)))    # 2 h
VIDEO_FETCH_INTERVAL = int(os.getenv("VIDEO_FETCH_INTERVAL", str(12 * 3600)))   # 12 h


# ---------------------------------------------------------------------------
# Core task functions
# ---------------------------------------------------------------------------


def run_reddit_scan() -> None:
    """Scan subreddits for relevant posts/comments and send email alerts."""
    from reddit_scanner import scan_subreddits
    from emailer import send_batch
    from notifier import notify_reddit_match

    logger.info("=== Reddit scan started ===")

    matches = scan_subreddits(TARGET_SUBREDDITS)
    logger.info("Relevant items found: %d", len(matches))

    if matches:
        sent = send_batch(matches)
        logger.info("Email notifications sent: %d/%d", sent, len(matches))

        # Also fire a desktop notification for the first match
        first = matches[0]
        notify_reddit_match(
            subreddit=first.get("subreddit", "?"),
            post_title=first.get("title", ""),
        )

    logger.info("=== Reddit scan finished ===")


def run_video_pipeline() -> None:
    """Fetch, download, edit recipe videos and notify when ready."""
    from video_fetcher import fetch_recipe_videos
    from video_editor import edit_video
    from notifier import notify_video_ready

    logger.info("=== Video pipeline started ===")

    videos = fetch_recipe_videos(max_per_query=2, max_total=3)
    logger.info("Videos downloaded: %d", len(videos))

    for video in videos:
        logger.info("Editing: %s", video["title"])
        final_path = edit_video(video)
        if final_path:
            notify_video_ready(final_path, dish_name=video["title"])
            logger.info("Video ready: %s", final_path)
        else:
            logger.warning("Editing failed for: %s", video["title"])

    logger.info("=== Video pipeline finished ===")


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------


def main() -> None:
    logger.info("NutriFitness Automation runner starting up.")
    logger.info("Target subreddits: %s", ", ".join(TARGET_SUBREDDITS))

    # Initialise the database on first run
    from reddit_scanner import init_db
    init_db()

    # Run both tasks immediately on startup, then on schedule
    next_reddit_scan = time.monotonic()
    next_video_fetch = time.monotonic()

    while True:
        now = time.monotonic()

        if now >= next_reddit_scan:
            try:
                run_reddit_scan()
            except Exception as exc:
                logger.error("Reddit scan cycle failed: %s", exc, exc_info=True)

            next_reddit_scan = time.monotonic() + REDDIT_SCAN_INTERVAL
            logger.info(
                "Next Reddit scan in %d min (≈ %s)",
                REDDIT_SCAN_INTERVAL // 60,
                datetime.fromtimestamp(time.time() + REDDIT_SCAN_INTERVAL).strftime("%H:%M"),
            )

        if now >= next_video_fetch:
            try:
                run_video_pipeline()
            except Exception as exc:
                logger.error("Video pipeline cycle failed: %s", exc, exc_info=True)

            next_video_fetch = time.monotonic() + VIDEO_FETCH_INTERVAL
            logger.info(
                "Next video fetch in %d h (≈ %s)",
                VIDEO_FETCH_INTERVAL // 3600,
                datetime.fromtimestamp(time.time() + VIDEO_FETCH_INTERVAL).strftime("%H:%M"),
            )

        # Sleep until the next scheduled event
        sleep_secs = min(
            next_reddit_scan - time.monotonic(),
            next_video_fetch - time.monotonic(),
        )
        sleep_secs = max(sleep_secs, 1)
        logger.debug("Sleeping for %.0f seconds...", sleep_secs)
        time.sleep(sleep_secs)


if __name__ == "__main__":
    main()
