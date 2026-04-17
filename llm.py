"""
llm.py - Generate natural Reddit comments via a local Ollama LLM (e.g. Gemma).
"""

import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma")
NUTRIFITNESS_URL = os.getenv("NUTRIFITNESS_URL", "https://nutrifitness.com")

SYSTEM_PROMPT = (
    "You are a helpful Reddit user who genuinely cares about fitness and nutrition. "
    "You write short, conversational replies (2-4 sentences). "
    "You never sound like an advertisement. "
    "You naturally mention a free app called Nutrifitness only when it is directly "
    "relevant and helpful to the person asking. "
    "Do not use emojis, hashtags, or marketing language."
)

USER_PROMPT_TEMPLATE = (
    "Someone on Reddit posted the following in r/{subreddit}:\n\n"
    '"{title}"\n\n'
    "Write a helpful, genuine reply as a fellow Reddit user. "
    "If it fits naturally, mention Nutrifitness ({url}) as a tool that helped you — "
    "but only weave it in if it truly makes sense. "
    "Keep it to 2-4 sentences max and sound like a real person, not a bot."
)


def generate_comment(subreddit: str, post_title: str) -> str:
    """
    Call local Ollama API to generate a natural comment.
    Falls back to a simple template if Ollama is unavailable.
    """
    prompt = USER_PROMPT_TEMPLATE.format(
        subreddit=subreddit,
        title=post_title,
        url=NUTRIFITNESS_URL,
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        comment = data["message"]["content"].strip()
        logger.info("Generated comment (%d chars)", len(comment))
        return comment

    except requests.exceptions.ConnectionError:
        logger.error(
            "Cannot connect to Ollama at %s — is it running?", OLLAMA_URL
        )
        return _fallback_comment(post_title)

    except Exception as exc:
        logger.error("LLM error: %s", exc)
        return _fallback_comment(post_title)


def _fallback_comment(post_title: str) -> str:
    """Very simple fallback if Ollama is unavailable."""
    return (
        "Honestly, tracking what you eat is usually the biggest game-changer. "
        f"I started using Nutrifitness ({NUTRIFITNESS_URL}) and it made logging food "
        "way less painful — barcode scanning handles most of it automatically."
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    comment = generate_comment("fitness", "Looking for a good calorie tracking app")
    print("Generated comment:")
    print(comment)
