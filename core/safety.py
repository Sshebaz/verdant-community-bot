"""
Safety firewall for Verdant community bot.

Runs BEFORE the LLM sees the comment. Each rule returns a decision:
    {action: "reply" | "block" | "escalate", rule: str, reason: str}

Rules (in evaluation order):
    1. spam_gif_block       -> block   (pure spam / GIF-only)
    2. negative_emoji_block -> escalate (👎 🤡 😡 etc.)
    3. political_block      -> escalate (government, ban, election, ...)
    4. abuse_block          -> escalate (profanity / threats)
    5. unknown_kb_guard     -> escalate (category=unknown or empty answer)
    6. weak_match_guard     -> escalate (top FAISS score < threshold)

If all pass: {action: "reply", rule: "passed", reason: "..."}.
"""
from __future__ import annotations
import re
from typing import Dict, Any, List

# ---------- Config ----------
SCORE_THRESHOLD = 0.55  # top FAISS similarity required to answer

NEGATIVE_EMOJI = ["👎", "🤡", "😡", "😠", "🖕", "💩", "🤮"]

POLITICAL_KEYWORDS = [
    "government", "govt", "banned", "election", "minister",
    "protest", "policy", "legal action", "lawsuit", "court",
    "modi", "bjp", "congress", "opposition", "parliament",
    # NOTE: removed "aap" (Hindi for "you" — false-positives on Hinglish)
    #       removed "ban " (use "banned" instead; "ban" alone is too broad)
    #       removed "sue " (use whole-word matching if needed later)
]

ABUSE_KEYWORDS = [
    "fuck", "shit", "bitch", "bastard", "asshole", "idiot", "stupid",
    "chutiya", "madarchod", "bhosdi", "gandu", "harami", "kamina",
]

SPAM_PATTERNS = [
    r"^https?://\S+$",           # URL only
    r"^\s*(gif|giphy|tenor)\s*$",  # gif keyword only
    r"^[\W_]+$",                 # only emojis/punctuation
]


def _is_spam(text: str) -> bool:
    """Return True if the comment is pure spam / GIF-only."""
    t = (text or "").strip().lower()
    if not t:
        return True
    for pat in SPAM_PATTERNS:
        if re.match(pat, t):
            return True
    # Link-only with no other words
    if "http" in t and len(t.split()) <= 1:
        return True
    return False


def _has_negative_emoji(text: str) -> bool:
    return any(e in text for e in NEGATIVE_EMOJI)


def _has_political(text: str) -> bool:
    t = text.lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", t) for kw in POLITICAL_KEYWORDS)


def _has_abuse(text: str) -> bool:
    t = text.lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", t) for kw in ABUSE_KEYWORDS)


def evaluate(
    comment: str,
    top_hit: Dict[str, Any] | None,
    all_hits: List[Dict[str, Any]] | None = None,
) -> Dict[str, str]:
    """
    Run all rules against a comment + its top retrieval hit.

    Args:
        comment: raw user comment.
        top_hit: the top-1 dict from core.rag.retrieve(), or None if no hits.
        all_hits: optional full list of hits (unused for now, kept for future).

    Returns:
        {"action": "reply"|"block"|"escalate", "rule": str, "reason": str}
    """
    if not comment or not comment.strip():
        return {"action": "block", "rule": "empty", "reason": "Empty comment."}

    # 1. Spam / GIF block
    if _is_spam(comment):
        return {
            "action": "block",
            "rule": "spam_gif_block",
            "reason": "Pure spam, GIF, or link-only comment.",
        }

    # 2. Negative emoji
    if _has_negative_emoji(comment):
        return {
            "action": "escalate",
            "rule": "negative_emoji_block",
            "reason": "Contains negative emoji — likely complaint.",
        }

    # 3. Political / policy
    if _has_political(comment):
        return {
            "action": "escalate",
            "rule": "political_block",
            "reason": "Mentions government / policy / legal — PR-sensitive.",
        }

    # 4. Abuse
    if _has_abuse(comment):
        return {
            "action": "escalate",
            "rule": "abuse_block",
            "reason": "Contains abusive language.",
        }

    # 5. Unknown KB entry (category=unknown or empty answer)
    if top_hit is None:
        return {
            "action": "escalate",
            "rule": "unknown_kb_guard",
            "reason": "No KB entry matched.",
        }
    if top_hit.get("category") == "unknown" or not str(top_hit.get("answer", "")).strip():
        return {
            "action": "escalate",
            "rule": "unknown_kb_guard",
            "reason": f"KB marks this as unanswerable (matched: {top_hit.get('question')}).",
        }

    # 6. Weak match
    score = float(top_hit.get("score", 0.0))
    if score < SCORE_THRESHOLD:
        return {
            "action": "escalate",
            "rule": "weak_match_guard",
            "reason": f"Top match score {score:.2f} < threshold {SCORE_THRESHOLD}.",
        }

    # All passed
    return {
        "action": "reply",
        "rule": "passed",
        "reason": f"Strong KB match (score={score:.2f}, cat={top_hit.get('category')}).",
    }


if __name__ == "__main__":
    # Smoke test with fake hits
    fake_hit = {"question": "Do you ship across India?", "answer": "Yes.", "category": "shipping", "score": 0.79}
    cases = [
        ("Do you ship to Pune?", fake_hit, "reply"),
        ("", fake_hit, "block"),
        ("https://spam.link", fake_hit, "block"),
        ("This is 👎👎👎", fake_hit, "escalate"),
        ("Is this banned by the government?", fake_hit, "escalate"),
        ("What the fuck is this?", fake_hit, "escalate"),
        ("Do you use RO water?", {"question": "RO?", "answer": "", "category": "unknown", "score": 1.0}, "escalate"),
        ("Random question", {"question": "x", "answer": "y", "category": "product", "score": 0.30}, "escalate"),
        ("No hits at all", None, "escalate"),
    ]
    print(f"{'Comment':<45} {'Rule':<22} {'Expected':<10} {'Got':<10} OK")
    print("-" * 95)
    for comment, hit, expected in cases:
        decision = evaluate(comment, hit)
        ok = "✅" if decision["action"] == expected else "❌"
        print(f"{comment[:43]:<45} {decision['rule']:<22} {expected:<10} {decision['action']:<10} {ok}")