"""
pages/5_ai_assistant.py
AI Recruiter Assistant — full chat UI with streaming responses.
"""
import streamlit as st

st.set_page_config(page_title="AI Assistant", layout="wide")

if "username" not in st.session_state:
    st.warning("Please log in from the home page.")
    st.stop()

st.title("🤖 AI Recruiter Assistant")
st.caption("Ask anything about candidates, jobs, clients, visa status, or rate guidance.")

# ── Ollama health check ───────────────────────────────────────────────────────
from ml.llm_client import health_check
status = health_check()
if not status["available"]:
    st.error("⚠️ Ollama is not running. Start it with: `docker compose up -d`")
    st.stop()
if not status["model_ready"]:
    st.warning(f"⚠️ Model `{status['model']}` not found. Pull it with: `docker compose exec ollama ollama pull llama3`")

# ── Session state ─────────────────────────────────────────────────────────────
session_id = st.session_state.get("username", "default")

if "chat_messages" not in st.session_state:
    # Load history from Redis if available
    try:
        from data.redis_client import get_chat_history
        st.session_state.chat_messages = get_chat_history(session_id)
    except Exception:
        st.session_state.chat_messages = []

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Assistant settings")
    if st.button("🗑️ Clear conversation"):
        st.session_state.chat_messages = []
        try:
            from data.redis_client import clear_chat_history
            clear_chat_history(session_id)
        except Exception:
            pass
        st.rerun()

    if st.button("🔄 Rebuild index"):
        with st.spinner("Rebuilding knowledge index..."):
            try:
                from ml.assistant import build_index
                build_index(force=True)
                st.success("Index rebuilt!")
            except Exception as e:
                st.error(f"Failed: {e}")

    st.divider()
    st.caption("💡 Try asking:")
    examples = [
        "Who has Python and AWS skills?",
        "Which candidates are on H1B visa?",
        "What's the rate for a senior React developer in New York?",
        "Which contractors have high attrition risk?",
        "Show me open Python jobs",
    ]
    for example in examples:
        if st.button(example, key=f"ex_{example[:20]}"):
            st.session_state.pending_question = example

# ── Chat display ──────────────────────────────────────────────────────────────
for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ── Handle example button clicks ──────────────────────────────────────────────
if "pending_question" in st.session_state:
    prompt = st.session_state.pop("pending_question")
else:
    prompt = st.chat_input("Ask about candidates, jobs, rates, visas...")

if prompt:
    # Show user message
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream assistant response
    with st.chat_message("assistant"):
        try:
            from ml.assistant import stream_answer
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.chat_messages[:-1]
            ]
            response = st.write_stream(stream_answer(prompt, history=history))
        except Exception as e:
            response = f"❌ Error: {e}"
            st.error(response)

    # Save to history
    st.session_state.chat_messages.append({"role": "assistant", "content": response})

    # Persist to Redis
    try:
        from data.redis_client import save_chat_history
        save_chat_history(session_id, st.session_state.chat_messages)
    except Exception:
        pass
