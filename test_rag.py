"""Smoke test for the RAG engine — no Groq, no LLM, pure retrieval."""
from core.rag import retrieve, build_index

TEST_COMMENTS = [
    "Do you ship to Mumbai?",
    "Is the bottle dishwasher safe?",
    "What is the tote made of?",
    "Can I get a refund on a used bottle?",
    "Do you use RO water in manufacturing?",  # unknown -> should score low
]

def main() -> None:
    build_index()
    print("\n" + "=" * 70)
    print("RAG RETRIEVAL TEST")
    print("=" * 70)
    for comment in TEST_COMMENTS:
        print(f"\nComment: {comment!r}")
        hits = retrieve(comment, k=3)
        if not hits:
            print("  (no hits)")
            continue
        for h in hits:
            print(f"  score={h['score']:.4f}  cat={h['category']:<15} Q={h['question']}")
    print("\n" + "=" * 70)
    print("Interpretation:")
    print("  score > 0.55  -> strong match (should answer from KB)")
    print("  score < 0.55  -> weak match (should escalate to human)")
    print("=" * 70)

if __name__ == "__main__":
    main()