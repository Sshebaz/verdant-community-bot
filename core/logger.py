"""
SQLite logging + escalation queue for Verdant bot.

Two tables:
    interactions: every comment the bot processes (any action)
    escalations:  comments flagged for human review

DB file lives at data/bot.db (gitignored).
"""
from __future__ import annotations
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bot.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                commenter TEXT,
                comment TEXT NOT NULL,
                detected_lang TEXT,
                action TEXT NOT NULL,
                rule TEXT,
                reason TEXT,
                top_hit_id TEXT,
                top_hit_question TEXT,
                top_hit_score REAL,
                reply TEXT,
                latency_ms INTEGER,
                tokens_in INTEGER,
                tokens_out INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS escalations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interaction_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY (interaction_id) REFERENCES interactions(id)
            )
        """)


def log_interaction(
    comment: str,
    commenter: str,
    detected_lang: str,
    action: str,
    rule: str,
    reason: str,
    top_hit: Optional[Dict[str, Any]] = None,
    reply: str = "",
    latency_ms: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> int:
    """Insert an interaction row. Returns the new row id."""
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO interactions
            (timestamp, commenter, comment, detected_lang, action, rule, reason,
             top_hit_id, top_hit_question, top_hit_score, reply,
             latency_ms, tokens_in, tokens_out)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts, commenter, comment, detected_lang, action, rule, reason,
                (top_hit or {}).get("id"),
                (top_hit or {}).get("question"),
                float((top_hit or {}).get("score", 0.0)),
                reply, latency_ms, tokens_in, tokens_out,
            ),
        )
        return int(cur.lastrowid)


def create_escalation(interaction_id: int, reason: str) -> int:
    """Create an escalation row linked to an interaction."""
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO escalations (interaction_id, reason, status, created_at) VALUES (?, ?, 'open', ?)",
            (interaction_id, reason, ts),
        )
        return int(cur.lastrowid)


def get_recent(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent interactions as dicts."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM interactions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_escalations(status: str = "open") -> List[Dict[str, Any]]:
    """Return escalations joined with their interaction row."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT e.id AS esc_id, e.reason, e.status, e.created_at,
                   i.comment, i.commenter, i.detected_lang, i.rule
            FROM escalations e
            JOIN interactions i ON i.id = e.interaction_id
            WHERE e.status = ?
            ORDER BY e.id DESC
            """,
            (status,),
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_escalation(esc_id: int) -> None:
    """Mark an escalation as resolved."""
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE escalations SET status='resolved', resolved_at=? WHERE id=?",
            (ts, esc_id),
        )


def stats() -> Dict[str, int]:
    """Return aggregate counts for the dashboard header."""
    init_db()
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        replied = conn.execute("SELECT COUNT(*) FROM interactions WHERE action='reply'").fetchone()[0]
        escalated = conn.execute("SELECT COUNT(*) FROM interactions WHERE action='escalate'").fetchone()[0]
        blocked = conn.execute("SELECT COUNT(*) FROM interactions WHERE action='block'").fetchone()[0]
        open_esc = conn.execute("SELECT COUNT(*) FROM escalations WHERE status='open'").fetchone()[0]
    return {
        "total": total, "replied": replied, "escalated": escalated,
        "blocked": blocked, "open_escalations": open_esc,
    }


if __name__ == "__main__":
    # Smoke test — write one interaction, one escalation, read back, resolve.
    init_db()
    iid = log_interaction(
        comment="Do you ship to Mumbai?",
        commenter="test_user",
        detected_lang="en",
        action="reply",
        rule="passed",
        reason="Strong KB match (score=0.80)",
        top_hit={"id": "kb_010", "question": "Do you ship across India?", "score": 0.80},
        reply="Yes, we ship pan-India in 3-5 business days.",
        latency_ms=1200, tokens_in=200, tokens_out=50,
    )
    print(f"logged interaction id={iid}")

    esc = create_escalation(iid, "Test escalation")
    print(f"created escalation id={esc}")
    print("stats:", stats())
    print("recent[0]:", get_recent(1)[0]["comment"])
    print("open escalations:", len(get_escalations("open")))
    resolve_escalation(esc)
    print("after resolve:", stats())