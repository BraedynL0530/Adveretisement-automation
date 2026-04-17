"""
video_editor.py - Add nutrition overlay and TTS voiceover to recipe videos.

Uses ffmpeg (via subprocess) to:
  1. Add a bottom nutrition overlay text.
  2. Merge TTS voiceover audio with the original video (ducking original audio).
  3. Output the edited video to the videos/ directory.

Requires ffmpeg to be installed and available on PATH.
"""

import os
import sqlite3
import logging
import subprocess
import json
import re
from pathlib import Path
from typing import Optional, Dict

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

VIDEO_OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./videos"))
DB_PATH = os.getenv("DB_PATH", "queue.db")
APPROXIMATE_CALORIES = int(os.getenv("APPROXIMATE_CALORIES", "420"))
APPROXIMATE_PROTEIN = int(os.getenv("APPROXIMATE_PROTEIN", "28"))
APPROXIMATE_CARBS = int(os.getenv("APPROXIMATE_CARBS", "35"))
APPROXIMATE_FAT = int(os.getenv("APPROXIMATE_FAT", "12"))
NUTRIFITNESS_URL = os.getenv("NUTRIFITNESS_URL", "nut-ri-fitness.app")


def _ensure_output_dir() -> Path:
    VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return VIDEO_OUTPUT_DIR


def _get_video_duration(video_path: Path) -> float:
    """Return the duration of a video in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception as exc:
        logger.warning("Could not get video duration for %s: %s", video_path, exc)
        return 0.0


def _escape_ffmpeg_text(text: str) -> str:
    """Escape special characters for ffmpeg drawtext filter."""
    # Escape: colon, single quote, backslash
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    return text


def _update_queue_status(
    source_url: str,
    status: str,
    output_path: Optional[str] = None,
    db_path: str = DB_PATH,
) -> None:
    try:
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
    except sqlite3.OperationalError as exc:
        logger.warning("Could not update queue status: %s", exc)


def add_nutrition_overlay(
    input_path: Path,
    output_path: Path,
    calories: int,
    protein: int,
    carbs: int,
    fat: int,
) -> bool:
    """
    Add a nutrition facts overlay bar at the bottom of the video.

    Returns True on success.
    """
    nutrition_text = (
        f"{calories} cal  |  {protein}g protein  |  {carbs}g carbs  |  {fat}g fat"
    )
    brand_text = f"nut-ri-fitness.app"

    # Escape for ffmpeg drawtext
    nt = _escape_ffmpeg_text(nutrition_text)
    bt = _escape_ffmpeg_text(brand_text)

    # Two-pass: semi-transparent background box + two text lines
    drawtext_filter = (
        # Dark semi-transparent background rectangle at bottom
        "drawbox=x=0:y=ih-80:w=iw:h=80:color=black@0.65:t=fill,"
        # Nutrition line
        f"drawtext=text='{nt}'"
        ":fontsize=28"
        ":fontcolor=white"
        ":x=(w-text_w)/2"
        ":y=h-65"
        ":box=0,"
        # Brand / URL line
        f"drawtext=text='{bt}'"
        ":fontsize=20"
        ":fontcolor=#ffcc00"
        ":x=(w-text_w)/2"
        ":y=h-30"
        ":box=0"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vf", drawtext_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.error("ffmpeg overlay failed:\n%s", result.stderr[-800:])
            return False
        logger.info("Nutrition overlay added → %s", output_path)
        return True
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg overlay timed out for %s", input_path)
        return False
    except FileNotFoundError:
        logger.error("ffmpeg not found — install it (brew install ffmpeg / apt install ffmpeg)")
        return False
    except Exception as exc:
        logger.error("Overlay error: %s", exc)
        return False


def merge_voiceover(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    duck_original: bool = True,
) -> bool:
    """
    Merge a TTS voiceover audio track with the video.

    If duck_original is True, lowers the original audio volume so the
    voiceover is clearly audible.

    Returns True on success.
    """
    video_duration = _get_video_duration(video_path)

    if duck_original:
        # Mix original audio (lowered to 20%) with voiceover (100%)
        filter_complex = (
            "[0:a]volume=0.2[orig];"
            "[1:a]volume=1.0[vo];"
            "[orig][vo]amix=inputs=2:duration=first[aout]"
        )
        audio_map = "[aout]"
    else:
        # Replace original audio entirely with voiceover
        filter_complex = "[1:a]volume=1.0[aout]"
        audio_map = "[aout]"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", audio_map,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.error("ffmpeg voiceover merge failed:\n%s", result.stderr[-800:])
            return False
        logger.info("Voiceover merged → %s", output_path)
        return True
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg merge timed out")
        return False
    except FileNotFoundError:
        logger.error("ffmpeg not found — install it")
        return False
    except Exception as exc:
        logger.error("Merge error: %s", exc)
        return False


def edit_video(
    video_info: Dict,
    db_path: str = DB_PATH,
) -> Optional[Path]:
    """
    Full editing pipeline for a single recipe video.

    Pipeline:
      1. Generate TTS voiceover
      2. Add nutrition overlay
      3. Merge voiceover audio into the overlaid video
      4. Save final video to videos/ directory

    Args:
        video_info: Dict with keys: url, title, local_path

    Returns:
        Path to the finished edited video, or None on failure.
    """
    from tts_generator import generate_voiceover

    source_url = video_info.get("url", "")
    title = video_info.get("title", "Recipe Video")
    raw_path = Path(video_info.get("local_path", ""))

    if not raw_path.exists():
        logger.error("Raw video not found: %s", raw_path)
        return None

    output_dir = _ensure_output_dir()

    # Derive a safe filename stem from the title
    safe_stem = re.sub(r"[^\w\- ]", "", title)[:50].strip().replace(" ", "_")
    if not safe_stem:
        safe_stem = raw_path.stem

    overlay_path = output_dir / f"{safe_stem}_overlay.mp4"
    final_path = output_dir / f"{safe_stem}_final.mp4"

    # Use approximate nutrition values (configurable via .env)
    calories = APPROXIMATE_CALORIES
    protein = APPROXIMATE_PROTEIN
    carbs = APPROXIMATE_CARBS
    fat = APPROXIMATE_FAT

    # Step 1: Generate voiceover
    logger.info("Generating voiceover for: %s", title)
    voiceover_path = generate_voiceover(
        dish_name=title,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        output_path=output_dir / f"{safe_stem}_vo.wav",
    )
    if not voiceover_path:
        logger.warning("TTS failed; will create video without voiceover")

    # Step 2: Add nutrition overlay
    logger.info("Adding nutrition overlay to: %s", raw_path.name)
    overlay_ok = add_nutrition_overlay(
        raw_path, overlay_path, calories, protein, carbs, fat
    )
    if not overlay_ok:
        logger.error("Overlay step failed for %s", raw_path)
        _update_queue_status(source_url, "failed", db_path=db_path)
        return None

    # Step 3: Merge voiceover (if available)
    if voiceover_path and voiceover_path.exists():
        merge_ok = merge_voiceover(overlay_path, voiceover_path, final_path)
        if not merge_ok:
            logger.warning("Voiceover merge failed; using overlay-only video")
            overlay_path.rename(final_path)
    else:
        overlay_path.rename(final_path)

    # Clean up intermediate overlay file if final exists
    if final_path.exists():
        if overlay_path.exists() and overlay_path != final_path:
            try:
                overlay_path.unlink()
            except OSError:
                pass
        logger.info("Edited video ready: %s", final_path)
        _update_queue_status(source_url, "done", str(final_path), db_path=db_path)
        return final_path
    else:
        logger.error("Final video not created for %s", source_url)
        _update_queue_status(source_url, "failed", db_path=db_path)
        return None


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 3:
        print("Usage: python video_editor.py <input_video.mp4> <dish_name>")
        sys.exit(1)

    test_info = {
        "url": "https://www.youtube.com/watch?v=test",
        "title": sys.argv[2],
        "local_path": sys.argv[1],
    }
    result = edit_video(test_info)
    if result:
        print(f"Edited video saved to: {result}")
    else:
        print("Editing failed")
        sys.exit(1)
