"""
Language detection + Groq-based translation for Verdant bot.

Supports:
    - English
    - Hindi (Devanagari script)
    - Hinglish (Roman-script Hindi)

Detection is heuristic (fast, offline). Translation uses Groq.
"""
from __future__ import annotations
import os
import re
from typing import Literal

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# ---------- Config ----------
MODEL = "openai/gpt-oss-20b"

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or not api_key.startswith("gsk_"):
            raise RuntimeError("GROQ_API_KEY missing or invalid in .env")
        _client = Groq(api_key=api_key)
    return _client


# ---------- Detection ----------
LangCode = Literal["en", "hi", "hinglish"]

# Common Hinglish tokens (Roman script Hindi)
HINGLISH_TOKENS = {
    "hai", "nahi", "kya", "kaise", "kab", "kahan", "kyun", "kyu",
    "bhai", "yaar", "dost", "please", "batao", "bata", "karo", "kar",
    "mujhe", "mera", "meri", "tum", "aap", "hum", "humara",
    "acha", "accha", "theek", "thik", "bahut", "bohot", "zyada",
    "chahiye", "milega", "milegi", "hoga", "hogi", "sakta", "sakti",
    "paisa", "paise", "rupee", "rate", "kimat", "kitna", "kitne",
    "bhejo", "bhej", "delivery", "order", "return", "refund",
    "kharab", "kharida", "pasand", "nahin", "haan", "han",
}


def detect_language(text: str) -> LangCode:
    """
    Heuristic language detection.

    - If Devanagari characters are present -> 'hi'
    - Else if enough Roman-Hindi tokens are present -> 'hinglish'
    - Else -> 'en'
    """
    if not text or not text.strip():
        return "en"

    # Devanagari block: U+0900 to U+097F
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"

    # Hinglish heuristic: count known tokens
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return "en"
    hits = sum(1 for w in words if w in HINGLISH_TOKENS)
    # If at least 1 in 3 words is a Hinglish token, call it Hinglish
    if hits >= max(2, len(words) // 3):
        return "hinglish"

    return "en"


# ---------- Translation ----------
def _call_groq(prompt: str, max_tokens: int = 200, retries: int = 2) -> str:
    client = _get_client()
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise translator. Reply with the translation only, no explanation, no quotes."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text
            print(f"[language] empty translation on attempt {attempt + 1}, retrying...")
        except Exception as e:
            print(f"[language] translation error on attempt {attempt + 1}: {e}")
    return ""


def to_english(text: str, source_lang: LangCode) -> str:
    """
    Translate Hindi or Hinglish text to English.
    English is returned unchanged (no API call).
    """
    if source_lang == "en" or not text.strip():
        return text

    lang_label = "Hindi (Devanagari script)" if source_lang == "hi" else "Hinglish (Roman-script Hindi)"
    prompt = (
        f"Translate the following {lang_label} comment to natural English. "
        f"Preserve meaning, keep it concise. Return only the English translation.\n\n"
        f"Comment:\n{text}"
    )
    return _call_groq(prompt, max_tokens=200)


def from_english(text: str, target_lang: LangCode) -> str:
    """
    Translate English reply back to the original language.
    English is returned unchanged.
    """
    if target_lang == "en" or not text.strip():
        return text

    if target_lang == "hi":
        prompt = (
            "Translate the following English customer-service reply to Hindi "
            "in Devanagari script. Keep the tone warm and professional. "
            "Return only the Hindi translation.\n\n"
            f"Reply:\n{text}"
        )
    else:  # hinglish
        prompt = (
            "Translate the following English customer-service reply to Hinglish "
            "(Hindi written in Roman script, natural Indian online tone, mix of English and Hindi words as a real person would write). "
            "Keep it warm and professional. Return only the Hinglish translation.\n\n"
            f"Reply:\n{text}"
        )

    result = _call_groq(prompt, max_tokens=400)
    if result and result[-1] not in ".!?।":
        print(f"[language] {target_lang} translation looks truncated, falling back to English")
        return ""
    return result


if __name__ == "__main__":
    # Smoke test — detection + one translation round-trip
    samples = [
        "Do you ship to Mumbai?",
        "Kya aap Mumbai me deliver karte ho?",
        "क्या आप मुंबई में डिलीवरी करते हैं?",
        "Bhai bottle ka rate kya hai?",
        "Is the tote GOTS certified?",
    ]
    print("=== Detection ===")
    for s in samples:
        lang = detect_language(s)
        print(f"[{lang:<9}] {s}")

    print("\n=== Translation round-trip (Hinglish) ===")
    src = "Kya aap Mumbai me deliver karte ho?"
    lang = detect_language(src)
    print(f"Source ({lang}):   {src}")
    en = to_english(src, lang)
    print(f"To English:        {en}")
    back = from_english("Yes, we deliver across India in 3-5 business days. Free over Rs 999.", lang)
    print(f"Reply in {lang}:   {back}")