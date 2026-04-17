"""
dashboard.py - Flask approval dashboard for reviewing generated comments.

Routes:
  GET  /              - List pending comments
  POST /approve/<id>  - Approve a comment (queues for posting)
  POST /reject/<id>   - Reject and remove a comment
  POST /edit/<id>     - Update comment text before approving
"""

import sqlite3
import os
import logging
from flask import Flask, render_template_string, redirect, url_for, request, jsonify
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
app = Flask(__name__)

DB_PATH = os.getenv("DB_PATH", "queue.db")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))

# ---------------------------------------------------------------------------
# HTML template (inline to keep the project self-contained)
# ---------------------------------------------------------------------------

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ad Automation Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0f0f0f; color: #e0e0e0; padding: 24px; }
    h1 { color: #ff4500; margin-bottom: 8px; }
    .subtitle { color: #888; margin-bottom: 24px; font-size: 14px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 24px; }
    .tab { padding: 8px 18px; border-radius: 6px; cursor: pointer;
           background: #1a1a1a; border: 1px solid #333; color: #aaa;
           text-decoration: none; font-size: 13px; }
    .tab.active { background: #ff4500; color: #fff; border-color: #ff4500; }
    .card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px;
            padding: 20px; margin-bottom: 16px; }
    .card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
    .post-title { font-weight: 600; font-size: 15px; color: #fff; }
    .meta { font-size: 12px; color: #888; margin-top: 4px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    .badge.pending  { background: #333; color: #ffa500; }
    .badge.approved { background: #1a3a1a; color: #4caf50; }
    .badge.posted   { background: #1a2a3a; color: #64b5f6; }
    .badge.rejected { background: #3a1a1a; color: #f44336; }
    .badge.failed   { background: #3a1a1a; color: #f44336; }
    .comment-box { margin-top: 14px; background: #111; border: 1px solid #333;
                   border-radius: 6px; padding: 12px; font-size: 13px;
                   line-height: 1.6; color: #ccc; white-space: pre-wrap; }
    .actions { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
    button, .btn { padding: 8px 16px; border-radius: 6px; border: none;
                   cursor: pointer; font-size: 13px; font-weight: 500; }
    .btn-approve { background: #4caf50; color: #fff; }
    .btn-reject  { background: #f44336; color: #fff; }
    .btn-edit    { background: #333; color: #fff; border: 1px solid #555; }
    button:hover { opacity: 0.85; }
    .edit-area { width: 100%; margin-top: 10px; background: #111; color: #e0e0e0;
                 border: 1px solid #555; border-radius: 6px; padding: 10px;
                 font-size: 13px; line-height: 1.6; resize: vertical; display: none; }
    .post-link { color: #64b5f6; font-size: 12px; word-break: break-all; }
    .empty { text-align: center; padding: 60px 20px; color: #555; }
    .stats { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
    .stat { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px;
            padding: 14px 20px; text-align: center; min-width: 100px; }
    .stat-num { font-size: 24px; font-weight: 700; color: #ff4500; }
    .stat-label { font-size: 11px; color: #888; margin-top: 2px; }
  </style>
</head>
<body>
  <h1>🤖 Ad Automation Dashboard</h1>
  <p class="subtitle">Review and approve generated Reddit comments before posting.</p>

  <!-- Stats -->
  <div class="stats">
    {% for label, count in stats.items() %}
    <div class="stat">
      <div class="stat-num">{{ count }}</div>
      <div class="stat-label">{{ label }}</div>
    </div>
    {% endfor %}
  </div>

  <!-- Tabs -->
  <div class="tabs">
    {% for tab in ['pending', 'approved', 'posted', 'rejected'] %}
    <a href="?status={{ tab }}"
       class="tab {% if current_status == tab %}active{% endif %}">
      {{ tab.capitalize() }}
    </a>
    {% endfor %}
  </div>

  <!-- Cards -->
  {% if items %}
    {% for item in items %}
    <div class="card">
      <div class="card-header">
        <div>
          <div class="post-title">{{ item['post_title'] }}</div>
          <div class="meta">
            r/{{ item['subreddit'] }} &bull;
            <a class="post-link" href="{{ item['post_url'] }}" target="_blank" rel="noopener">
              {{ item['post_url'][:80] }}{% if item['post_url']|length > 80 %}…{% endif %}
            </a>
          </div>
        </div>
        <span class="badge {{ item['status'] }}">{{ item['status'] }}</span>
      </div>

      <div class="comment-box" id="preview-{{ item['id'] }}">{{ item['generated_comment'] }}</div>

      {% if item['status'] in ['pending', 'approved'] %}
      <div class="actions">
        {% if item['status'] == 'pending' %}
        <form method="POST" action="/approve/{{ item['id'] }}" style="display:inline">
          <button class="btn-approve">✅ Approve</button>
        </form>
        {% endif %}
        <form method="POST" action="/reject/{{ item['id'] }}" style="display:inline">
          <input type="hidden" name="status" value="{{ current_status }}">
          <button class="btn-reject">❌ Reject</button>
        </form>
        <button class="btn-edit" onclick="toggleEdit({{ item['id'] }})">✏️ Edit</button>
      </div>

      <form method="POST" action="/edit/{{ item['id'] }}" id="edit-form-{{ item['id'] }}">
        <textarea class="edit-area" id="edit-{{ item['id'] }}" name="comment"
                  rows="5">{{ item['generated_comment'] }}</textarea>
        <div class="actions" id="edit-actions-{{ item['id'] }}" style="display:none">
          <button type="submit" class="btn-approve">💾 Save &amp; Approve</button>
          <button type="button" class="btn-edit" onclick="toggleEdit({{ item['id'] }})">Cancel</button>
        </div>
      </form>
      {% endif %}
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">No {{ current_status }} items found.</div>
  {% endif %}

  <script>
    function toggleEdit(id) {
      const box  = document.getElementById('edit-' + id);
      const acts = document.getElementById('edit-actions-' + id);
      const prev = document.getElementById('preview-' + id);
      const isHidden = box.style.display === 'none' || box.style.display === '';
      box.style.display  = isHidden ? 'block' : 'none';
      acts.style.display = isHidden ? 'flex'  : 'none';
      if (prev) prev.style.display = isHidden ? 'none' : 'block';
    }
  </script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_stats():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM queue GROUP BY status"
        ).fetchall()
    counts = {r["status"]: r["cnt"] for r in rows}
    return {
        "Pending":  counts.get("pending", 0),
        "Approved": counts.get("approved", 0),
        "Posted":   counts.get("posted", 0),
        "Rejected": counts.get("rejected", 0),
        "Failed":   counts.get("failed", 0),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    from filter import init_db
    init_db(DB_PATH)

    current_status = request.args.get("status", "pending")
    with get_db() as conn:
        items = conn.execute(
            "SELECT * FROM queue WHERE status = ? ORDER BY created_at DESC",
            (current_status,),
        ).fetchall()

    return render_template_string(
        TEMPLATE,
        items=items,
        stats=get_stats(),
        current_status=current_status,
    )


@app.route("/approve/<int:item_id>", methods=["POST"])
def approve(item_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE queue SET status = 'approved' WHERE id = ? AND status = 'pending'",
            (item_id,),
        )
        conn.commit()
    return redirect(url_for("index", status="pending"))


@app.route("/reject/<int:item_id>", methods=["POST"])
def reject(item_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE queue SET status = 'rejected' WHERE id = ?", (item_id,)
        )
        conn.commit()
    # Use the 'status' form field (sent by the template) to redirect back to
    # the correct tab; fall back to 'pending' to avoid any open-redirect risk.
    status = request.form.get("status", "pending")
    if status not in ("pending", "approved", "posted", "rejected", "failed"):
        status = "pending"
    return redirect(url_for("index", status=status))


@app.route("/edit/<int:item_id>", methods=["POST"])
def edit(item_id: int):
    new_comment = request.form.get("comment", "").strip()
    if new_comment:
        with get_db() as conn:
            conn.execute(
                "UPDATE queue SET generated_comment = ?, status = 'approved' WHERE id = ?",
                (new_comment, item_id),
            )
            conn.commit()
    return redirect(url_for("index", status="approved"))


@app.route("/api/stats")
def api_stats():
    """JSON endpoint for real-time status polling."""
    return jsonify(get_stats())


@app.route("/api/queue")
def api_queue():
    """JSON endpoint returning queue items for a given status."""
    status = request.args.get("status", "pending")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM queue WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from filter import init_db
    init_db(DB_PATH)
    logging.basicConfig(level=logging.INFO)
    print(f"Dashboard running at http://localhost:{FLASK_PORT}")
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)
