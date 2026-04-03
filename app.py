"""
Layer 8: UI (Streamlit Chat Interface)
Single-column chat. While the twin is working, live status lines grow in place
inside the assistant bubble. They disappear the moment the answer arrives.
Debug info lives in a collapsible expander below each answer.
"""
import streamlit as st
from pathlib import Path
from twin import DigitalTwin


def main():
    st.set_page_config(
        page_title="Digital Twin — Archit",
        page_icon="🤖",
        layout="centered",
    )

    # ── Header ─────────────────────────────────────────────────────────────────
    avatar_path = Path("assets/archit_avatar.png")
    col1, col2 = st.columns([1, 6])
    with col1:
        if avatar_path.exists():
            st.image(str(avatar_path), width=80)
        else:
            st.markdown("# 🤖")
    with col2:
        st.title("Archit at Sara")
        st.caption("Ask questions about my work, messages, and activities.")

    # ── Load twin ──────────────────────────────────────────────────────────────
    @st.cache_resource
    def load_twin():
        return DigitalTwin()

    try:
        twin = load_twin()
    except Exception as e:
        st.error(f"Failed to initialize Digital Twin: {e}")
        st.stop()

    # ── Session state ──────────────────────────────────────────────────────────
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 💡 Example Questions")
        st.markdown("""
- What happened in late December around inference?
- What happened in Q4 2025?
- Tell me about cold starts
- What are your AWS credentials?
        """)
        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.rerun()

    # ── Chat history ───────────────────────────────────────────────────────────
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("citations"):
                with st.expander("📎 Citations"):
                    for cit in msg["citations"]:
                        st.markdown(f"**Source:** `{cit['source']}`")
                        st.markdown(f"**Quote:** _{cit['text']}_")
                        if cit.get("timestamp"):
                            st.markdown(f"**Time:** {cit['timestamp']}")
                        st.divider()
            if msg.get("debug"):
                with st.expander("🔍 Debug Info"):
                    st.json(msg["debug"])

    # ── New question ───────────────────────────────────────────────────────────
    if prompt := st.chat_input("Ask a question…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            # Placeholder that shows live status lines while the twin works.
            # We replace its content on every step, building up a growing log.
            # It is cleared completely once the answer is ready.
            live_slot = st.empty()
            log_lines: list[str] = []

            def on_step(step: str, data: dict) -> None:
                """Append a line for this step and re-render the whole log."""
                if step == "query_parsed":
                    kws = data.get("keywords") or []
                    kw_str = "  ".join(f"`{k}`" for k in kws) if kws else "—"
                    log_lines.append(f"🔎 **Keywords:** {kw_str}")
                    if data.get("rewritten"):
                        log_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;_Rewritten:_ {data['rewritten']}")
                    if data.get("date_range"):
                        log_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;_Date range:_ `{data['date_range']}`")

                elif step == "mode":
                    m = data.get("answer_mode", "")
                    icon = "🗒️" if "SUMMARY" in m else "🎯"
                    log_lines.append(f"{icon} **Mode:** `{m}`")

                elif step == "retrieved":
                    weeks = [w for w in (data.get("weeks") or []) if w]
                    week_str = "  ".join(f"`{w}`" for w in weeks) if weeks else "_all chunks_"
                    log_lines.append(f"📅 **Weeks:** {week_str}")
                    log_lines.append(
                        f"📄 **Chunks:** {data.get('candidates', 0)} candidates "
                        f"→ **{data.get('selected', 0)} selected**"
                    )

                elif step == "evidence":
                    count = data.get("count", 0)
                    icon = "✅" if data.get("has_evidence") else "❌"
                    log_lines.append(f"{icon} **Evidence:** {count} supporting quote(s)")

                elif step == "answer_ready":
                    conf = data.get("confidence", "unknown")
                    log_lines.append(f"✍️ **Generating answer** · confidence `{conf}`")

                # Re-render the whole growing log in the placeholder
                with live_slot.container():
                    for line in log_lines:
                        st.markdown(line)

            try:
                result = twin.answer(prompt, debug=True, step_callback=on_step)
            except Exception as e:
                live_slot.empty()
                st.error(str(e))
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Error: {e}",
                })
                st.stop()

            # ── Clear live log, show answer ────────────────────────────────────
            live_slot.empty()

            answer = result.get("answer", "I do not see this in your data.")
            confidence = result.get("confidence", "unknown")
            citations = result.get("citations", [])
            reasoning = result.get("reasoning", "")

            st.markdown(answer)

            if confidence == "high":
                st.success(f"Confidence: {confidence.upper()}")
            elif confidence == "medium":
                st.info(f"Confidence: {confidence.upper()}")
            else:
                st.warning(f"Confidence: {confidence.upper()}")

            if reasoning:
                st.caption(reasoning)

            if citations:
                with st.expander("📎 Citations"):
                    for cit in citations:
                        st.markdown(f"**Source:** `{cit['source']}`")
                        st.markdown(f"**Quote:** _{cit['text']}_")
                        if cit.get("timestamp"):
                            st.markdown(f"**Time:** {cit['timestamp']}")
                        st.divider()

            if result.get("debug"):
                with st.expander("🔍 Debug Info"):
                    st.json(result["debug"])

            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "citations": citations,
                "debug": result.get("debug"),
            })


if __name__ == "__main__":
    main()
