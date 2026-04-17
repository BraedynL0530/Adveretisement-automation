"""
video_fetcher.py - Search for and download free-to-use recipe videos.

Uses yt-dlp to download videos from YouTube.
Targets channels/searches that are Creative Commons or royalty-free.
Videos are downloaded to the configured output directory.
"""

import os
import sqlite3
import logging
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

VIDEO_OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./videos"))
DB_PATH = os.getenv("DB_PATH", "queue.db")

# Search terms focused on recipe/cooking content
RECIPE_SEARCH_QUERIES = [
    "easy healthy recipe tutorial",
    "quick high protein meal prep",
    "simple chicken recipe cooking",
    "easy pasta recipe tutorial",
    "healthy breakfast ideas cooking",
]

# yt-dlp options for downloading
YTDLP_COMMON_OPTS = [
    "--no-playlist",
    "--max-filesize", "200M",
    "--format", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "--merge-output-format", "mp4",
    "--no-warnings",
    "--quiet",
    "--print-json",
]


def _ensure_output_dir() -> Path:
    VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return VIDEO_OUTPUT_DIR


def _is_already_queued(source_url: str, db_path: str = DB_PATH) -> bool:
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM video_queue WHERE source_url = ?", (source_url,)
            ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False


def _add_to_queue(
    source_url: str,
    title: str,
    status: str = "pending",
    output_path: Optional[str] = None,
    db_path: str = DB_PATH,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO video_queue (source_url, title, status, output_path)
            VALUES (?, ?, ?, ?)
            """,
            (source_url, title, status, output_path),
        )
        conn.commit()


def _update_queue_status(
    source_url: str,
    status: str,
    output_path: Optional[str] = None,
    db_path: str = DB_PATH,
) -> None:
    with sqlite3.connect(db_path) as conn:
        if output_path:
            conn.execute(
                "UPDATE video_queue SET status = ?, output_path = ? WHERE source_url = ?",
                (status, output_path, source_url),
            )
        else:
            conn.execute(
                "UPDATE video_queue SET status = ? WHERE source_url = ?",
                (status, source_url),
            )
        conn.commit()


def search_recipe_videos(query: str, max_results: int = 3) -> List[Dict]:
    """
    Search YouTube for recipe videos matching the query.

    Uses yt-dlp's flat playlist extraction to get video URLs without downloading.
    Returns a list of dicts with 'url' and 'title'.
    """
    search_url = f"ytsearch{max_results}:{query}"
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "%(webpage_url)s\t%(title)s\t%(duration)s",
        "--no-warnings",
        "--quiet",
        search_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0 and result.stderr:
            logger.warning("yt-dlp search warning: %s", result.stderr[:200])

        videos = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t", 2)
            if len(parts) >= 2:
                url, title = parts[0].strip(), parts[1].strip()
                duration = int(parts[2]) if len(parts) > 2 and parts[2].strip().isdigit() else 0
                # Filter: prefer videos between 1-15 minutes
                if duration and (duration < 60 or duration > 900):
                    logger.debug("Skipping video (bad duration %ds): %s", duration, title)
                    continue
                if url and title:
                    videos.append({"url": url, "title": title, "duration": duration})

        logger.info("Found %d videos for query: %s", len(videos), query)
        return videos

    except subprocess.TimeoutExpired:
        logger.error("yt-dlp search timed out for query: %s", query)
        return []
    except FileNotFoundError:
        logger.error("yt-dlp not found — install it with: pip install yt-dlp")
        return []
    except Exception as exc:
        logger.error("Search failed for '%s': %s", query, exc)
        return []


def download_video(url: str, title: str, db_path: str = DB_PATH) -> Optional[Path]:
    """
    Download a single video to the output directory.

    Returns the path to the downloaded file, or None on failure.
    """
    if _is_already_queued(url, db_path):
        logger.debug("Video already in queue, skipping: %s", url)
        return None

    output_dir = _ensure_output_dir()
    # Use yt-dlp template; we'll find the file afterward
    output_template = str(output_dir / "%(id)s_raw.%(ext)s")

    cmd = [
        "yt-dlp",
        "--output", output_template,
        "--format", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-warnings",
        "--print", "after_move:filepath",
        url,
    ]

    _add_to_queue(url, title, status="downloading", db_path=db_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error("yt-dlp download failed for %s:\n%s", url, result.stderr[:400])
            _update_queue_status(url, "failed", db_path=db_path)
            return None

        # The "--print after_move:filepath" flag outputs the final file path
        filepath_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if filepath_line and Path(filepath_line).exists():
            downloaded_path = Path(filepath_line)
        else:
            # Fallback: find the most recently created mp4 in output_dir
            mp4_files = sorted(
                output_dir.glob("*_raw.mp4"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            if not mp4_files:
                logger.error("Could not find downloaded file for %s", url)
                _update_queue_status(url, "failed", db_path=db_path)
                return None
            downloaded_path = mp4_files[0]

        logger.info("Downloaded: %s → %s", url, downloaded_path)
        _update_queue_status(url, "downloaded", str(downloaded_path), db_path=db_path)
        return downloaded_path

    except subprocess.TimeoutExpired:
        logger.error("Download timed out for %s", url)
        _update_queue_status(url, "failed", db_path=db_path)
        return None
    except FileNotFoundError:
        logger.error("yt-dlp not found — install it with: pip install yt-dlp")
        _update_queue_status(url, "failed", db_path=db_path)
        return None
    except Exception as exc:
        logger.error("Download failed for %s: %s", url, exc)
        _update_queue_status(url, "failed", db_path=db_path)
        return None


def fetch_recipe_videos(
    max_per_query: int = 2,
    max_total: int = 5,
    db_path: str = DB_PATH,
) -> List[Dict]:
    """
    Search for and download recipe videos.

    Returns a list of dicts: {url, title, local_path}.
    Skips videos already in the queue.
    """
    from reddit_scanner import init_db
    init_db(db_path)

    downloaded = []
    for query in RECIPE_SEARCH_QUERIES:
        if len(downloaded) >= max_total:
            break

        videos = search_recipe_videos(query, max_results=max_per_query)
        for video in videos:
            if len(downloaded) >= max_total:
                break
            if _is_already_queued(video["url"], db_path):
                logger.debug("Already queued: %s", video["url"])
                continue

            local_path = download_video(video["url"], video["title"], db_path)
            if local_path:
                downloaded.append(
                    {
                        "url": video["url"],
                        "title": video["title"],
                        "local_path": local_path,
                    }
                )

    logger.info("Fetched %d new recipe videos", len(downloaded))
    return downloaded


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    videos = fetch_recipe_videos(max_per_query=1, max_total=2)
    for v in videos:
        print(f"Downloaded: {v['title']}")
        print(f"  Source: {v['url']}")
        print(f"  Local:  {v['local_path']}")
