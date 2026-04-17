"""
scraper.py - Fetch posts from target subreddits via RSS feeds.
No PRAW or Reddit API needed - uses public RSS endpoints.
"""

import feedparser
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

REDDIT_RSS_URL = "https://www.reddit.com/r/{subreddit}/new.rss?limit=50"

KEYWORDS = [
    "tips", "alternative", "app", "tracking", "calories", "calorie",
    "diet", "fitness", "nutrition", "macro", "workout", "weight", "lose",
    "healthy", "eating", "food", "exercise", "recommend", "suggestion",
    "help", "how to", "what do", "what should", "any app", "any tool",
    "losing weight", "gain muscle", "protein", "carbs",
]


def fetch_subreddit_posts(subreddit: str) -> List[Dict]:
    """Fetch recent posts from a subreddit RSS feed."""
    url = REDDIT_RSS_URL.format(subreddit=subreddit)
    posts = []

    try:
        feed = feedparser.parse(url)

        if feed.bozo and feed.bozo_exception:
            logger.warning(
                "Feed parse warning for r/%s: %s", subreddit, feed.bozo_exception
            )

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published = entry.get("published", "")

            if not title or not link:
                continue

            # Skip [deleted] or [removed] titles
            if title.lower() in ("[deleted]", "[removed]"):
                continue

            posts.append(
                {
                    "subreddit": subreddit,
                    "title": title,
                    "url": link,
                    "published": published,
                }
            )

        logger.info("Fetched %d posts from r/%s", len(posts), subreddit)

    except Exception as exc:
        logger.error("Error fetching r/%s: %s", subreddit, exc)

    return posts


def fetch_all_subreddits(subreddits: List[str]) -> List[Dict]:
    """Fetch posts from multiple subreddits and return combined list."""
    all_posts = []
    for subreddit in subreddits:
        posts = fetch_subreddit_posts(subreddit.strip())
        all_posts.extend(posts)
    return all_posts


def is_relevant(title: str) -> bool:
    """Return True if the post title contains at least one target keyword."""
    lower_title = title.lower()
    return any(kw in lower_title for kw in KEYWORDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample_subreddits = ["fitness", "loseit", "nutrition", "Entrepreneur"]
    posts = fetch_all_subreddits(sample_subreddits)
    relevant = [p for p in posts if is_relevant(p["title"])]
    print(f"Total posts: {len(posts)}, Relevant: {len(relevant)}")
    for p in relevant[:5]:
        print(f"  [{p['subreddit']}] {p['title']}")
        print(f"  URL: {p['url']}")
