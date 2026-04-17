# Advertisement-automation

Automated Reddit comment bot that monitors fitness/nutrition subreddits for relevant posts and generates natural comments mentioning [Nutrifitness](https://nutrifitness.com).

## Features

- 🔍 **RSS scraper** — no PRAW / Reddit API needed ($0)
- 🤖 **Local LLM comments** — Ollama + Gemma generate human-sounding replies
- ✅ **Manual approval** — Flask dashboard lets you approve/edit/reject before anything is posted
- 🎭 **Playwright autoposter** — posts comments via browser automation, saves auth session
- 🗄️ **SQLite queue** — persistent job queue with status tracking
- ⏱️ **Scheduler** — runs every 2–4 hours to scrape, every 30 min to post
- 🛡️ **Rate limiting** — hard cap of 3 posts/day, random delays between posts

## Stack

| Component | Library |
|-----------|---------|
| RSS scraping | `feedparser` |
| LLM | `ollama` (local, Gemma or any model) |
| Browser automation | `playwright` |
| Dashboard | `flask` |
| Queue | SQLite (stdlib) |
| Config | `python-dotenv` |

## Quick Start

### 1. Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) installed and running locally
- A Reddit account

### 2. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Pull a model into Ollama

```bash
ollama pull gemma
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your Reddit credentials and preferred settings
```

### 5. Start the dashboard (one terminal)

```bash
python dashboard.py
# Open http://localhost:5000
```

### 6. Start the runner (another terminal)

```bash
python runner.py
```

The runner will immediately scrape RSS feeds, generate comments, and save them to the queue. Open the dashboard to approve or edit them before anything is posted to Reddit.

## File Structure

```
Advertisement-automation/
├── scraper.py        # RSS feed fetcher
├── filter.py         # Relevance filter + duplicate check + DB init
├── llm.py            # Ollama comment generator
├── poster.py         # Playwright Reddit autoposter
├── runner.py         # Scheduler loop
├── dashboard.py      # Flask approval dashboard
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md

# Auto-created at runtime (git-ignored):
# queue.db            — SQLite queue
# auth.json           — Playwright browser session
```

## Dashboard

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | View queue by status (pending/approved/posted/rejected) |
| `/approve/<id>` | POST | Approve a pending comment |
| `/reject/<id>` | POST | Reject a comment |
| `/edit/<id>` | POST | Edit comment text and approve in one step |
| `/api/stats` | GET | JSON stats for real-time polling |
| `/api/queue` | GET | JSON queue items for a given `?status=` |

## Safety

- **No auto-posting** — every comment must be manually approved first
- **3 posts/day cap** — configurable via `POSTS_PER_DAY` in `.env`
- **Random delays** — 30–120 seconds between posts (configurable)
- **Duplicate detection** — same post URL is never queued twice
- **Keyword filtering** — only posts matching fitness/nutrition keywords are targeted

## Environment Variables

See [`.env.example`](.env.example) for all available settings.
