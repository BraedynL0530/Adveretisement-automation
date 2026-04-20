"""
emailer.py - Send email notifications for relevant Reddit posts/comments.

Uses smtplib with SMTP_SSL or STARTTLS depending on the configured port.
Configure via .env:
  SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "")
NUTRIFITNESS_URL = os.getenv("NUTRIFITNESS_URL", "nut-ri-fitness.app")


def _build_email(item: Dict) -> MIMEMultipart:
    """Build a MIMEMultipart email message for a single Reddit item."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"[NutriFitness Bot] Relevant Reddit {item['type'].capitalize()}: "
        f"r/{item.get('subreddit', '?')} — {item.get('title', '')[:60]}"
    )
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL

    subreddit = item.get("subreddit", "unknown")
    item_type = item.get("type", "post").capitalize()
    title = item.get("title", "(no title)")
    body_snippet = item.get("body", "").strip()
    url = item.get("url", "")
    suggested_reply = item.get("suggested_reply", "").strip()

    # Plain-text version
    plain_parts = [
        f"New relevant Reddit {item_type} in r/{subreddit}",
        "",
        f"Title:  {title}",
        f"Link:   {url}",
        "",
    ]
    if body_snippet:
        plain_parts += [f"Context:\n{body_snippet[:400]}", ""]
    if suggested_reply:
        plain_parts += ["Suggested reply (optional):", suggested_reply, ""]
    plain_parts += [
        "---",
        "You decide whether to reply. This notification was sent by your",
        f"NutriFitness Reddit Scanner. Visit {NUTRIFITNESS_URL}",
    ]
    plain_text = "\n".join(plain_parts)

    # HTML version
    body_snippet_html = body_snippet[:400].replace("\n", "<br>")
    body_html = f"<p>{body_snippet_html}</p>" if body_snippet else ""
    suggested_reply_html = suggested_reply.replace("\n", "<br>")
    reply_html = (
        f"<h3>💬 Suggested Reply (optional)</h3>"
        f"<blockquote style='background:#f4f4f4;padding:10px;border-left:4px solid #0079d3'>"
        f"{suggested_reply_html}"
        f"</blockquote>"
    ) if suggested_reply else ""

    html_text = f"""\
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#222">
  <div style="background:#0079d3;padding:16px;border-radius:6px 6px 0 0">
    <h2 style="color:white;margin:0">🔍 Reddit Match Found</h2>
    <p style="color:#cce4ff;margin:4px 0 0">r/{subreddit} &mdash; {item_type}</p>
  </div>
  <div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 6px 6px">
    <h3 style="margin-top:0">{title}</h3>
    <p><a href="{url}" style="color:#0079d3;font-weight:bold">→ View on Reddit</a></p>
    {body_html}
    {reply_html}
    <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
    <p style="font-size:12px;color:#888">
      You decide whether to reply — this bot does <strong>not</strong> post automatically.<br>
      Sent by your NutriFitness Reddit Scanner &bull;
      <a href="https://{NUTRIFITNESS_URL}">{NUTRIFITNESS_URL}</a>
    </p>
  </div>
</body>
</html>"""

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_text, "html"))
    return msg


def send_notification(item: Dict) -> bool:
    """
    Send an email notification for a single Reddit item.

    Returns True on success, False on failure.
    """
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL]):
        logger.error(
            "Email not configured — set SENDER_EMAIL, SENDER_PASSWORD, "
            "RECIPIENT_EMAIL in .env"
        )
        return False

    msg = _build_email(item)

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())

        logger.info(
            "Email sent for r/%s %s: %s",
            item.get("subreddit"),
            item.get("type"),
            item.get("title", "")[:60],
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP authentication failed — check SENDER_EMAIL / SENDER_PASSWORD. "
            "For Gmail, use an App Password (not your account password)."
        )
        return False
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        return False


def send_batch(items: List[Dict]) -> int:
    """Send email notifications for a list of items. Returns count of successes."""
    sent = 0
    for item in items:
        if send_notification(item):
            sent += 1
    return sent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_item = {
        "type": "post",
        "subreddit": "fitness",
        "title": "Looking for a good calorie tracking app",
        "body": "I've been trying to track macros but most apps are confusing. Any recommendations?",
        "url": "https://www.reddit.com/r/fitness/comments/example",
        "suggested_reply": "I'd suggest trying Nutrifitness — barcode scanning makes logging really easy.",
    }
    result = send_notification(test_item)
    print("Email sent:", result)
