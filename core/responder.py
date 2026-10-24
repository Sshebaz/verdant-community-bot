"""
Reply generator for Verdant bot.

Takes the retrieved KB answer + original comment, and produces a
short, brand-safe reply in the user's language.

Design rules:
    - Answer ONLY from the provided KB answer. No invention.
    - Max 2 sentences.
    - Warm, professional D2C brand tone.
    - Reply in the same language as the user (en / hi / hinglish).
"""
from __future__ import annotations
import os
import time
from typing import Dict, Any

from dotenv import load_dotenv
from groq import Groq

from core.language import LangCode, from_english

load_dotenv()

# ---------- Config ----------
MODEL = "openai/gpt-oss-20b"
MAX_TOKENS = 180
TEMPERATURE = 0.3  # low — we want consistency, not creativity

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or not api_key.startswith("gsk_"):
            raise RuntimeError("GROQ_API_KEY missing or invalid in .env")
        _client = Groq(api_key=api_key)
    return _client


SYSTEM_PROMPT = (
    "You are the official community manager for Verdant, a sustainable D2C brand "
    "in India (bamboo cutlery, recycled glass bottles, organic cotton totes).\n\n"
    "Rules:\n"
    "1. Answer ONLY using the FACTS provided. Never invent details.\n"
    "2. If the facts do not contain the answer, do not guess — instead say you'll "
    "have the team follow up.\n"
    "3. Keep the reply warm, friendly, professional — 1 to 2 short sentences.\n"
    "4. Do not repeat the customer's question. Do not start with 'Sure!' or 'Of course!'.\n"
    "5. Do not use emojis unless the customer used one first.\n"
    "6. Reply in English. It will be translated afterwards."
)


def _build_user_prompt(comment: str, kb_answer: str, kb_question: str) -> str:
    return (
        f"Customer comment:\n{comment}\n\n"
        f"Relevant fact from our knowledge base:\n"
        f"Q: {kb_question}\nA: {kb_answer}\n\n"
        f"Write the reply now (1-2 sentences, English only)."
    )


def generate_reply(
    comment: str,
    top_hit: Dict[str, Any],
    target_lang: LangCode,
) -> Dict[str, Any]:
    """
    Generate a reply for `comment` using the KB answer in `top_hit`.

    Returns:
        {
            "reply": str,               # in target_lang
            "reply_en": str,            # English version (for logs)
            "latency_ms": int,
            "tokens_in": int,
            "tokens_out": int,
            "model": str,
        }
    """
    t0 = time.time()

    kb_answer = str(top_hit.get("answer", "")).strip()
    kb_question = str(top_hit.get("question", "")).strip()

    if not kb_answer:
        raise ValueError("generate_reply called with empty KB answer — should have been escalated.")

    client = _get_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(comment, kb_answer, kb_question)},
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )

    reply_en = (resp.choices[0].message.content or "").strip()
    if not reply_en:
        raise RuntimeError("Groq returned empty reply.")

    # Translate back to user's language if needed
    reply_final = from_english(reply_en, target_lang)
    if not reply_final:
        print(f"[responder] translation to {target_lang} returned empty, falling back to English")
        reply_final = reply_en

    latency_ms = int((time.time() - t0) * 1000)
    usage = resp.usage

    return {
        "reply": reply_final,
        "reply_en": reply_en,
        "latency_ms": latency_ms,
        "tokens_in": getattr(usage, "prompt_tokens", 0) if usage else 0,
        "tokens_out": getattr(usage, "completion_tokens", 0) if usage else 0,
        "model": MODEL,
    }


