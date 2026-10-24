"""Smoke test for responder — run from project root."""
from core.rag import retrieve
from core.language import detect_language, to_english
from core.responder import generate_reply

TEST_CASES = [
    "Do you ship to Mumbai?",
    "Kya aap Mumbai me deliver karte ho?",
    "क्या आप मुंबई में डिलीवरी करते हैं?",
]

def main() -> None:
    for comment in TEST_CASES:
        lang = detect_language(comment)
        query_en = to_english(comment, lang)
        hits = retrieve(query_en, k=1)
        if not hits:
            print(f"[{lang}] {comment!r} -> no hits")
            continue
        result = generate_reply(comment, hits[0], lang)
        print(f"\n[{lang}] {comment!r}")
        print(f"  EN reply:     {result['reply_en']}")
        print(f"  {lang} reply: {result['reply']}")
        print(f"  latency: {result['latency_ms']}ms  tokens: "
              f"{result['tokens_in']}in/{result['tokens_out']}out")

if __name__ == "__main__":
    main()