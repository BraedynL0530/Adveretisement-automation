"""
notifier.py - Desktop notifications for when edited videos are ready.

Uses plyer for cross-platform notifications (Windows, macOS, Linux).
Falls back to a console log if plyer is unavailable.
"""

import os
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

NUTRIFITNESS_URL = os.getenv("NUTRIFITNESS_URL", "nut-ri-fitness.app")
VIDEO_OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./videos"))

APP_NAME = "NutriFitness Bot"


def notify_video_ready(video_path: Path, dish_name: Optional[str] = None) -> None:
    """
    Send a desktop notification indicating that an edited recipe video is ready.

    Args:
        video_path: Path to the finished video file.
        dish_name: Optional dish name for the notification title.
    """
    title = f"🎬 Recipe Video Ready!"
    message = (
        f"{dish_name + ' — ' if dish_name else ''}"
        f"Your edited video is saved to:\n{video_path}\n"
        f"Post it to Instagram / TikTok to promote {NUTRIFITNESS_URL}"
    )

    _send_notification(title, message, str(video_path))


def notify_reddit_match(subreddit: str, post_title: str) -> None:
    """
    Send a desktop notification for a new Reddit match (email already sent).

    Args:
        subreddit: Name of the subreddit.
        post_title: Title of the matched post/comment.
    """
    title = f"📬 Reddit Match in r/{subreddit}"
    message = f"{post_title[:100]}\nCheck your email for details and a suggested reply."
    _send_notification(title, message)


def _send_notification(title: str, message: str, toast_icon: Optional[str] = None) -> None:
    """Attempt to send a desktop notification via plyer, fall back to logging."""
    try:
        from plyer import notification as plyer_notif

        # Build kwargs; ticker is used on some platforms
        kwargs = {
            "app_name": APP_NAME,
            "title": title,
            "message": message,
            "timeout": 10,
        }
        # plyer accepts an app_icon path on some platforms
        if toast_icon:
            kwargs["app_icon"] = toast_icon

        plyer_notif.notify(**kwargs)
        logger.info("Desktop notification sent: %s", title)

    except ImportError:
        logger.warning(
            "plyer not installed — desktop notifications disabled. "
            "Install with: pip install plyer"
        )
        _fallback_console(title, message)

    except Exception as exc:
        # Notification may silently fail on headless servers; just log it
        logger.warning("Desktop notification failed (%s) — logging instead", exc)
        _fallback_console(title, message)


def _fallback_console(title: str, message: str) -> None:
    """Print notification to console when desktop notifications aren't available."""
    border = "=" * 60
    print(f"\n{border}")
    print(f"  NOTIFICATION: {title}")
    print(f"  {message.replace(chr(10), chr(10) + '  ')}")
    print(f"{border}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    notify_video_ready(
        video_path=Path("videos/HotHoneyChicken_final.mp4"),
        dish_name="Hot Honey Chicken Sliders",
    )
    notify_reddit_match(
        subreddit="fitness",
        post_title="Looking for a calorie tracking app",
    )
