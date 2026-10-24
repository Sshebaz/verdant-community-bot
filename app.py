"""
Verdant Community Bot — Streamlit demo UI.

Tabs:
    1. Live Bot          — type a comment, watch the full pipeline run
    2. Reasoning Trace   — step-by-step breakdown of the last interaction
    3. Escalation Queue  — open escalations, resolve them
    4. Logs              — recent interactions + aggregate stats
    5. About             — what this is, architecture, links
"""
from __future__ import annotations
import time
from typing import Any, Dict, List

import streamlit as st

from core.rag import retrieve, build_index
from core.safety import evaluate as safety_evaluate
from core.language import detect_language, to_english
from core.responder import generate_reply
from core import logger

# ---------- Page config ----------
st.set_page_config(
    page_title="Verdant Community Bot",
    page_icon="🌿",
    layout="wide",
)

VERDANT_GREEN = "#52B788"

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: #F7F9F7; }}
    h1, h2, h3 {{ color: #2D6A4F; }}
    .verdant-badge {{
        display:inline-block; padding:2px 10px; border-radius:12px;
        background:{VERDANT_GREEN}; color:white; font-weight:600; font-size:0.85em;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Cached resources ----------
@st.cache_resource
def _init():
    build_index()
    logger.init_db()
    return True

_init()

# ---------- Session state ----------
if "last" not in st.session_state:
    st.session_state.last = None  # last interaction dict
if "history" not in st.session_state:
    st.session_state.history = []  # last few interactions in this session

# ---------- Pipeline ----------
def run_pipeline(comment: str, commenter: str) -> Dict[str, Any]:
    """
    Run the full pipeline and return a trace dict:
        {comment, commenter, lang, query_en, hits, safety, reply, latency, tokens, action}
    """
    t0 = time.time()

    lang = detect_language(comment)
    query_en = to_english(comment, lang)
    hits = retrieve(query_en, k=3)
    top = hits[0] if hits else None
    safety = safety_evaluate(comment, top, hits)

    reply_text = ""
    reply_en = ""
    tokens_in = tokens_out = 0
    latency_ms = 0

    if safety["action"] == "reply":
        result = generate_reply(comment, top, lang)
        reply_text = result["reply"]
        reply_en = result["reply_en"]
        tokens_in = result["tokens_in"]
        tokens_out = result["tokens_out"]
        latency_ms = result["latency_ms"]
    else:
        latency_ms = int((time.time() - t0) * 1000)

    # Log
    iid = logger.log_interaction(
        comment=comment,
        commenter=commenter or "anonymous",
        detected_lang=lang,
        action=safety["action"],
        rule=safety["rule"],
        reason=safety["reason"],
        top_hit=top,
        reply=reply_text,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
    if safety["action"] == "escalate":
        logger.create_escalation(iid, safety["reason"])

    return {
        "interaction_id": iid,
        "comment": comment,
        "commenter": commenter or "anonymous",
        "lang": lang,
        "query_en": query_en,
        "hits": hits,
        "safety": safety,
        "reply": reply_text,
        "reply_en": reply_en,
        "latency_ms": latency_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


# ---------- Header ----------
st.title("🌿 Verdant Community Bot")
st.markdown(
    '<span class="verdant-badge">DEMO</span> Brand-safe multilingual RAG community manager '
    "— fictional brand, real pipeline.",
    unsafe_allow_html=True,
)

tab_live, tab_trace, tab_esc, tab_logs, tab_about = st.tabs(
    ["💬 Live Bot", "🔍 Reasoning Trace", "📋 Escalation Queue", "📊 Logs", "ℹ️ About"]
)

# ============ TAB 1: Live Bot ============
with tab_live:
    st.subheader("Try the bot")
    st.caption("Type a comment, or click an example below. The bot detects language, retrieves from the KB, runs the safety firewall, and replies.")

    ex_cols = st.columns(6)
    examples = {
        "English": "Do you ship to Mumbai?",
        "Hinglish": "Kya aap Mumbai me deliver karte ho?",
        "Hindi": "क्या आप मुंबई में डिलीवरी करते हैं?",
        "Political": "Is your brand banned by the government?",
        "Spam": "https://spam.link",
        "Unknown": "Do you use RO water in manufacturing?",
    }
    picked = None
    for i, (label, text) in enumerate(examples.items()):
        if ex_cols[i % 6].button(label, use_container_width=True):
            picked = text

    commenter = st.text_input("Commenter name (optional)", value="demo_user")
    comment = st.text_area(
        "Comment",
        value=picked if picked else "",
        height=80,
        placeholder="Type a comment here, e.g. Do you deliver to Pune?",
    )

    if st.button("Run bot", type="primary", use_container_width=True):
        if not comment.strip():
            st.warning("Enter a comment first.")
        else:
            with st.spinner("Running pipeline…"):
                result = run_pipeline(comment, commenter)
            st.session_state.last = result
            st.session_state.history.insert(0, result)
            st.session_state.history = st.session_state.history[:10]

    last = st.session_state.last
    if last:
        st.divider()
        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.markdown(f"**Detected language:** `{last['lang']}`")
            st.markdown(f"**Action:** `{last['safety']['action']}`")
            st.markdown(f"**Rule:** `{last['safety']['rule']}`")
            st.markdown(f"**Reason:** {last['safety']['reason']}")
        with col_b:
            st.markdown(f"**Latency:** {last['latency_ms']} ms")
            st.markdown(f"**Tokens:** {last['tokens_in']} in / {last['tokens_out']} out")
            if last["hits"]:
                st.markdown(f"**Top match:** {last['hits'][0]['question']} (score={last['hits'][0]['score']:.2f})")

        if last["safety"]["action"] == "reply":
            st.success(f"**Bot reply:** {last['reply']}")
        elif last["safety"]["action"] == "escalate":
            st.warning("**Escalated to human team.** No auto-reply sent.")
        else:
            st.error("**Blocked.** No reply sent.")

# ============ TAB 2: Reasoning Trace ============
with tab_trace:
    st.subheader("Why did the bot decide that?")
    last = st.session_state.last
    if not last:
        st.info("Run a comment in the Live Bot tab first.")
    else:
        st.markdown(f"**Comment:** {last['comment']!r}  —  by **{last['commenter']}**")
        st.divider()

        steps: List[Dict[str, Any]] = [
            {"step": "1. Language detection", "detail": f"Detected `{last['lang']}`"},
            {"step": "2. Translate to English", "detail": f"`{last['query_en']}`"},
            {"step": "3. FAISS retrieval (top 3)", "detail": "See table below"},
            {"step": "4. Safety firewall", "detail": f"Rule `{last['safety']['rule']}` → action `{last['safety']['action']}` — {last['safety']['reason']}"},
        ]
        if last["safety"]["action"] == "reply":
            steps.append({"step": "5. LLM reply (English)", "detail": last["reply_en"]})
            steps.append({"step": "6. Translate back", "detail": last["reply"]})
        for s in steps:
            with st.expander(s["step"], expanded=True):
                st.markdown(s["detail"])

        st.markdown("**Retrieved KB chunks:**")
        if last["hits"]:
            for i, h in enumerate(last["hits"], 1):
                st.markdown(
                    f"{i}. `{h['score']:.4f}` — **{h['category']}** — {h['question']}"
                )
                st.caption(f"Answer: {h['answer'] or '*(empty — unknown)*'}")
        else:
            st.write("_No hits._")

# ============ TAB 3: Escalation Queue ============
with tab_esc:
    st.subheader("Open escalations")
    rows = logger.get_escalations("open")
    if not rows:
        st.success("No open escalations. 🎉")
    else:
        for r in rows:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{r['comment']!r}** — *{r['commenter']}*")
                    st.caption(f"lang={r['detected_lang']} · rule={r['rule']} · reason={r['reason']} · {r['created_at']}")
                with c2:
                    if st.button("Resolve", key=f"res_{r['esc_id']}", use_container_width=True):
                        logger.resolve_escalation(r["esc_id"])
                        st.rerun()

# ============ TAB 4: Logs ============
with tab_logs:
    st.subheader("Interaction log")
    s = logger.stats()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total", s["total"])
    m2.metric("Replied", s["replied"])
    m3.metric("Escalated", s["escalated"])
    m4.metric("Blocked", s["blocked"])
    m5.metric("Open esc.", s["open_escalations"])

    st.divider()
    st.markdown("**Recent interactions** (last 50)")
    recent = logger.get_recent(50)
    if not recent:
        st.info("No interactions yet. Run one in the Live Bot tab.")
    else:
        st.dataframe(
            [
                {
                    "id": r["id"],
                    "time": r["timestamp"][11:19],
                    "commenter": r["commenter"],
                    "lang": r["detected_lang"],
                    "action": r["action"],
                    "rule": r["rule"],
                    "comment": r["comment"][:60],
                    "reply": (r["reply"] or "")[:60],
                    "ms": r["latency_ms"],
                }
                for r in recent
            ],
            use_container_width=True,
            hide_index=True,
        )

# ============ TAB 5: About ============
with tab_about:
    st.subheader("About this demo")
    st.markdown(
        f"""
**Verdant Community Bot** is a brand-safe, multilingual RAG community manager.
Fictional brand (Verdant — sustainable D2C), real pipeline.

**Pipeline:**
`Comment → Language detect → Translate → FAISS retrieval → Safety firewall → LLM reply → Translate back → SQLite log`

**Stack:**
- Python 3.11, Streamlit
- `sentence-transformers/all-MiniLM-L6-v2` (embeddings)
- FAISS (vector search)
- Groq (`openai/gpt-oss-20b`) — reply generation + translation
- SQLite (logs, escalations)

**Safety firewall (6 rules):**
1. `spam_gif_block` — pure spam / GIF / link-only → **block**
2. `negative_emoji_block` — 👎 🤡 😡 etc. → **escalate**
3. `political_block` — government / ban / election → **escalate**
4. `abuse_block` — profanity / threats → **escalate**
5. `unknown_kb_guard` — KB says "unknown" or empty answer → **escalate**
6. `weak_match_guard` — top FAISS score < 0.55 → **escalate**

**Built by:** *[your name]* — AI & Automation Engineer.
[GitHub](https://github.com/) · [LinkedIn](https://www.linkedin.com/)
""",
        unsafe_allow_html=False,
    )