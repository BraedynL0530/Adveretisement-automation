# NutriFitness Advertisement Automation Bot

Automated tooling for promoting **[nut-ri-fitness.app](https://nut-ri-fitness.app)** — a calorie-tracking app that makes logging food easy via barcode scanning.

## What It Does

### 🔍 Reddit Scanner → Email Notifications
- Scans r/fitness, r/loseit, r/nutrition, r/Entrepreneur (and more) every **2 hours**
- Uses your local **Ollama Gemma 3** to check if posts/comments are relevant to Nutrifitness
- When a match is found: sends you an **email** with:
  - Reddit link
  - Post/comment context
  - Optional AI-suggested reply
- **You** decide whether to reply — nothing is posted automatically

### 🎬 Recipe Video Auto-Generator
- Fetches free cooking recipe videos from YouTube every **12 hours**
- Auto-downloads via **yt-dlp**
- Auto-edits with **ffmpeg**:
  - Bottom overlay: `420 cal | 28g protein | 35g carbs | 12g fat` + `nut-ri-fitness.app`
  - TTS voiceover describing the recipe + Nutrifitness plug
- **Desktop notification** when each video is ready
- Videos saved to `videos/` — **you post manually** to Instagram/TikTok

## Stack

| Component | Library |
|-----------|---------|
| Reddit scanning | `requests` (JSON API, no auth) |
| AI relevance check | `ollama` (local Gemma 3) |
| Email notifications | `smtplib` (stdlib) |
| Video downloading | `yt-dlp` |
| Video editing | `ffmpeg` (subprocess) |
| Text-to-speech | `pyttsx3` or `gTTS` |
| Desktop notifications | `plyer` |
| Queue tracking | SQLite (stdlib) |
| Config | `python-dotenv` |

## File Structure

```
Advertisement-automation/
├── reddit_scanner.py   # Reddit JSON API + Ollama relevance check
├── emailer.py          # SMTP email notifications
├── video_fetcher.py    # yt-dlp recipe video downloader
├── video_editor.py     # ffmpeg overlay + voiceover merger
├── tts_generator.py    # pyttsx3 / gTTS voiceover generator
├── notifier.py         # plyer desktop notifications
├── runner.py           # Scheduler (2h Reddit, 12h video)
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md

# Auto-created at runtime (git-ignored):
# queue.db      — SQLite queue
# videos/       — edited video output
```

## Quick Start

### 1. Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) installed and running locally with **Gemma 3** already downloaded
- `ffmpeg` installed and on your PATH:
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — set your SMTP credentials at minimum
```

**Gmail setup:**  
Use an [App Password](https://myaccount.google.com/apppasswords) (not your regular password).  
Enable 2-Factor Authentication first, then generate an App Password for "Mail".

### 4. Run

```bash
python runner.py
```

The runner will immediately:
1. Scan Reddit for relevant posts/comments → email you if found
2. Download and edit recipe videos → notify you when ready

## Configuration

All settings live in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Local Ollama address |
| `OLLAMA_MODEL` | `gemma3:4b` | Model name (must already be downloaded) |
| `TARGET_SUBREDDITS` | `fitness,loseit,...` | Comma-separated subreddits to scan |
| `SMTP_SERVER` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port (587 = STARTTLS, 465 = SSL) |
| `SENDER_EMAIL` | — | Your Gmail address |
| `SENDER_PASSWORD` | — | Gmail App Password |
| `RECIPIENT_EMAIL` | — | Where to send alerts (can be same as sender) |
| `VIDEO_OUTPUT_DIR` | `./videos/` | Where edited videos are saved |
| `TTS_ENGINE` | `pyttsx3` | `pyttsx3` (offline) or `gtts` (Google) |
| `TTS_VOICE` | `male` | `male` or `female` |
| `APPROXIMATE_CALORIES` | `420` | Nutrition overlay — calories |
| `APPROXIMATE_PROTEIN` | `28` | Nutrition overlay — protein (g) |
| `APPROXIMATE_CARBS` | `35` | Nutrition overlay — carbs (g) |
| `APPROXIMATE_FAT` | `12` | Nutrition overlay — fat (g) |
| `NUTRIFITNESS_URL` | `nut-ri-fitness.app` | Branding URL used in overlays + TTS |
| `REDDIT_SCAN_INTERVAL` | `7200` | Reddit scan frequency (seconds) |
| `VIDEO_FETCH_INTERVAL` | `43200` | Video fetch frequency (seconds) |

## How It Works

### Reddit Flow
```
Runner (every 2h)
  → reddit_scanner.py fetches posts + comments via Reddit JSON API
  → Ollama checks relevance (local, $0 cost)
  → On match: emailer.py sends you an email
  → notifier.py fires a desktop notification
  → YOU decide to reply manually
```

### Video Flow
```
Runner (every 12h)
  → video_fetcher.py searches YouTube for recipe videos
  → yt-dlp downloads the video
  → tts_generator.py generates TTS voiceover (pyttsx3 or gTTS)
  → video_editor.py adds nutrition overlay + merges audio (ffmpeg)
  → Video saved to videos/ folder
  → notifier.py sends desktop notification
  → YOU post to Instagram / TikTok manually
```

## Key Rules

- ❌ **No auto-posting** — you review everything before it goes live
- ❌ **No Reddit credentials** needed — read-only scanning via public JSON API
- ✅ **$0 cost** — local Ollama, no paid APIs
- ✅ **Copyright-safe videos** — uses yt-dlp with original TTS audio layer
- ✅ **Cross-platform** — Windows, macOS, Linux

## Troubleshooting

**Ollama not connecting:**  
Make sure the Ollama desktop app is running. Check with `curl http://localhost:11434`.

**Email not sending (Gmail):**  
Use an App Password, not your account password. Enable 2FA first.

**ffmpeg not found:**  
Install ffmpeg and make sure it's on your PATH. Test with `ffmpeg -version`.

**No desktop notifications (Linux):**  
Install `libnotify`: `sudo apt install libnotify-bin`

**yt-dlp download errors:**  
Update yt-dlp: `pip install -U yt-dlp`

