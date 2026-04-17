"""
tts_generator.py - Generate TTS voiceover audio for recipe videos.

Supports pyttsx3 (offline) and gTTS (Google TTS, requires internet).
Configure via .env: TTS_ENGINE (pyttsx3 or gtts), TTS_VOICE (male or female)
"""

import os
import logging
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TTS_ENGINE = os.getenv("TTS_ENGINE", "pyttsx3").lower()
TTS_VOICE = os.getenv("TTS_VOICE", "male").lower()
NUTRIFITNESS_URL = os.getenv("NUTRIFITNESS_URL", "nut-ri-fitness.app")

OUTRO_LINE = (
    f"Made with Nutrifitness Pantry — the easy way to track what you eat. "
    f"For more recipes like this, download Nutrifitness and track calories "
    f"by scanning barcodes. Visit {NUTRIFITNESS_URL}"
)


def build_voiceover_script(
    dish_name: str,
    calories: int,
    protein: int,
    carbs: int,
    fat: int,
    steps: Optional[list] = None,
) -> str:
    """
    Build a voiceover script for a recipe video.

    Args:
        dish_name: Name of the dish (e.g. "Hot Honey Chicken Sliders")
        calories: Approximate calories per serving
        protein: Approximate protein in grams
        carbs: Approximate carbs in grams
        fat: Approximate fat in grams
        steps: Optional list of short step descriptions

    Returns:
        Full voiceover script as a string.
    """
    intro = (
        f"Today we're making {dish_name}. "
        f"This recipe has approximately {calories} calories per serving, "
        f"with {protein} grams of protein, {carbs} grams of carbs, "
        f"and {fat} grams of fat."
    )

    body_lines = []
    if steps:
        for i, step in enumerate(steps):
            if i == 0:
                body_lines.append(f"First, {step}.")
            elif i == len(steps) - 1:
                body_lines.append(f"Finally, {step}.")
            else:
                body_lines.append(f"Then, {step}.")

    parts = [intro] + body_lines + [OUTRO_LINE]
    return "  ".join(parts)


def generate_audio_pyttsx3(script: str, output_path: Path) -> bool:
    """Generate audio using pyttsx3 (offline TTS)."""
    try:
        import pyttsx3
    except ImportError:
        logger.error("pyttsx3 not installed — run: pip install pyttsx3")
        return False

    try:
        engine = pyttsx3.init()

        # Select voice based on preference
        voices = engine.getProperty("voices")
        if voices:
            if TTS_VOICE == "female":
                female_voices = [v for v in voices if "female" in v.name.lower()
                                  or "zira" in v.name.lower() or "samantha" in v.name.lower()]
                if female_voices:
                    engine.setProperty("voice", female_voices[0].id)
                elif len(voices) > 1:
                    engine.setProperty("voice", voices[1].id)
            else:
                male_voices = [v for v in voices if "male" in v.name.lower()
                               or "david" in v.name.lower() or "daniel" in v.name.lower()]
                if male_voices:
                    engine.setProperty("voice", male_voices[0].id)
                else:
                    engine.setProperty("voice", voices[0].id)

        # Slightly slower rate for clarity
        rate = engine.getProperty("rate")
        engine.setProperty("rate", max(120, rate - 20))

        engine.save_to_file(script, str(output_path))
        engine.runAndWait()

        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info("pyttsx3 audio saved to %s", output_path)
            return True
        else:
            logger.error("pyttsx3 produced an empty file at %s", output_path)
            return False

    except Exception as exc:
        logger.error("pyttsx3 TTS error: %s", exc)
        return False


def generate_audio_gtts(script: str, output_path: Path) -> bool:
    """Generate audio using gTTS (Google TTS, requires internet)."""
    try:
        from gtts import gTTS
    except ImportError:
        logger.error("gTTS not installed — run: pip install gTTS")
        return False

    try:
        tts = gTTS(text=script, lang="en", slow=False)
        # gTTS saves as MP3
        mp3_path = output_path.with_suffix(".mp3")
        tts.save(str(mp3_path))

        if mp3_path.exists() and mp3_path.stat().st_size > 0:
            # Rename to the expected path (caller may expect .mp3)
            if output_path.suffix.lower() == ".mp3":
                logger.info("gTTS audio saved to %s", mp3_path)
                return True
            else:
                mp3_path.rename(output_path)
                logger.info("gTTS audio saved to %s", output_path)
                return True
        else:
            logger.error("gTTS produced an empty file")
            return False

    except Exception as exc:
        logger.error("gTTS TTS error: %s", exc)
        return False


def generate_voiceover(
    dish_name: str,
    calories: int,
    protein: int,
    carbs: int,
    fat: int,
    output_path: Optional[Path] = None,
    steps: Optional[list] = None,
) -> Optional[Path]:
    """
    Generate a TTS voiceover for a recipe video.

    Returns the path to the generated audio file, or None on failure.
    The output file will be .aiff (pyttsx3 on macOS), .wav (pyttsx3 on Windows/Linux),
    or .mp3 (gTTS).
    """
    script = build_voiceover_script(dish_name, calories, protein, carbs, fat, steps)
    logger.info("Voiceover script (%d chars): %s...", len(script), script[:80])

    if output_path is None:
        suffix = ".mp3" if TTS_ENGINE == "gtts" else ".wav"
        tmp_dir = Path(tempfile.mkdtemp())
        output_path = tmp_dir / f"voiceover{suffix}"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if TTS_ENGINE == "gtts":
        success = generate_audio_gtts(script, output_path.with_suffix(".mp3"))
        if success:
            return output_path.with_suffix(".mp3")
    else:
        # pyttsx3: may produce .aiff on macOS; use .aiff extension for safety
        aiff_path = output_path.with_suffix(".aiff")
        success = generate_audio_pyttsx3(script, aiff_path)
        if success:
            return aiff_path
        # Fallback: try with .wav extension
        success = generate_audio_pyttsx3(script, output_path.with_suffix(".wav"))
        if success:
            return output_path.with_suffix(".wav")

    logger.error("All TTS engines failed for dish: %s", dish_name)
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    audio = generate_voiceover(
        dish_name="Hot Honey Chicken Sliders",
        calories=420,
        protein=28,
        carbs=35,
        fat=12,
        output_path=Path("/tmp/test_voiceover.wav"),
        steps=[
            "season your chicken thighs with salt, pepper, and garlic powder",
            "pan fry over medium heat until golden, about 6 minutes per side",
            "mix hot sauce, honey, and butter for the glaze",
            "toss the chicken in the glaze and serve on slider buns",
        ],
    )
    if audio:
        print(f"Voiceover generated: {audio}")
    else:
        print("TTS generation failed")
