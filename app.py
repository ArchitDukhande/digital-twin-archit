"""
Layer 8: UI (Streamlit Chat Interface)
Interactive chat with citations and optional debug panel.
"""
import streamlit as st
import json
from pathlib import Path
from twin import DigitalTwin


def main():
    st.set_page_config(
        page_title="Digital Twin - Archit",
        page_icon="🤖",
        layout="wide"
    )

    # Header with avatar
    avatar_path = Path("assets/archit_avatar.png")
    col1, col2 = st.columns([1, 6])
    with col1:
        if avatar_path.exists():
            st.image(str(avatar_path), width=100)
        else:
            st.markdown("🤖")
    with col2:
        st.title("Archit at Sara")
        st.caption("Ask questions about my work, messages, and activities.")

    # Initialize twin (cached)
    @st.cache_resource
    def load_twin():
        return DigitalTwin()

    try:
        twin = load_twin()
    except Exception as e:
        st.error(f"Failed to initialize Digital Twin: {e}")
        st.stop()

    # Sidebar controls
    with st.sidebar:
        st.header("Settings")
        show_debug = st.checkbox("Show Debug Info", value=False)
        show_citations = st.checkbox("Show Citations", value=True)
        
        st.divider()
        st.markdown("### Example Questions")
        st.markdown("""
        - What happened in late December around inference??
        - What happened in Q4 2025?
        - Tell me about cold starts
        - What are your AWS Credentials?
        """)

    # Chat interface
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("citations") and show_citations:
                with st.expander("📎 Citations"):
                    for cit in msg["citations"]:
                        st.markdown(f"**Source:** `{cit['source']}`")
                        st.markdown(f"**Quote:** _{cit['text']}_")
                        if cit.get("timestamp"):
                            st.markdown(f"**Time:** {cit['timestamp']}")
                        st.divider()
            if msg.get("debug") and show_debug:
                with st.expander("🔍 Debug Info"):
                    st.json(msg["debug"])

    # Chat input
    if prompt := st.chat_input("Ask a question..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get answer from twin
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    result = twin.answer(prompt, debug=show_debug)
                    
                    answer = result.get("answer", "I do not see it")
                    confidence = result.get("confidence", "unknown")
                    citations = result.get("citations", [])
                    reasoning = result.get("reasoning", "")
                    
                    # Display answer
                    st.markdown(answer)
                    
                    # Show confidence badge
                    if confidence == "high":
                        st.success(f"Confidence: {confidence.upper()}")
                    elif confidence == "medium":
                        st.info(f"Confidence: {confidence.upper()}")
                    else:
                        st.warning(f"Confidence: {confidence.upper()}")
                    
                    # Show reasoning
                    if reasoning:
                        st.caption(reasoning)
                    
                    # Show citations
                    if citations and show_citations:
                        with st.expander("📎 Citations"):
                            for cit in citations:
                                st.markdown(f"**Source:** `{cit['source']}`")
                                st.markdown(f"**Quote:** _{cit['text']}_")
                                if cit.get("timestamp"):
                                    st.markdown(f"**Time:** {cit['timestamp']}")
                                st.divider()
                    
                    # Show debug
                    if show_debug and result.get("debug"):
                        with st.expander("🔍 Debug Info"):
                            st.json(result["debug"])
                    
                    # Add to chat history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "citations": citations,
                        "debug": result.get("debug") if show_debug else None,
                    })
                    
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Error processing question: {e}",
                    })

    # Clear chat button
    if st.sidebar.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()


if __name__ == "__main__":
    main()
