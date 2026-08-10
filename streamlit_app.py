import uuid

import streamlit as st
from langgraph.types import Command

from graph import app
from i18n import t
from nodes import MOCK_MODE

st.set_page_config(page_title="Academic Research Agent", page_icon="📖")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

defaults = {
    "language": "en",
    "phase": "idle",          # idle -> running -> waiting_approval <-> running -> done
    "thread_id": str(uuid.uuid4()),
    "topic": "",
    "pending_payload": None,  # dict (initial state) or Command(resume=...)
    "interrupt_payload": None,
    "final_state": None,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def reset_session():
    st.session_state.phase = "idle"
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.topic = ""
    st.session_state.pending_payload = None
    st.session_state.interrupt_payload = None
    st.session_state.final_state = None


# ---------------------------------------------------------------------------
# Sidebar: language switch (locked once a run has started, to keep node
# output and UI text consistent within one research session)
# ---------------------------------------------------------------------------

with st.sidebar:
    lang_options = ["English", "中文"]
    current_index = 0 if st.session_state.language == "en" else 1
    picked = st.radio(
        "Language / 语言",
        lang_options,
        index=current_index,
        disabled=(st.session_state.phase != "idle"),
    )
    st.session_state.language = "en" if picked == "English" else "zh"

lang = st.session_state.language

if MOCK_MODE:
    st.warning(t(lang, "web_mock_mode_warning"))

st.title(t(lang, "web_title"))
st.caption(t(lang, "web_subtitle"))

config = {"configurable": {"thread_id": st.session_state.thread_id}}

NODE_LABEL_KEYS = {
    "decompose_directions": "node_decompose_directions",
    "search_arxiv": "node_search_arxiv",
    "search_crossref": "node_search_crossref",
    "search_semantic_scholar": "node_search_semantic_scholar",
    "process_papers": "node_process_papers",
    "summarize_literature": "node_summarize_literature",
    "generate_report": "node_generate_report",
    "verify_citations": "node_verify_citations",
}

DOMAIN_LABEL_KEYS = {
    "cs": "domain_cs",
    "humanities": "domain_humanities",
    "interdisciplinary": "domain_interdisciplinary",
}


def run_stream(payload):
    """Drives the graph forward (from the start or after a resume), rendering
    each completed node live in a status box. Returns the interrupt payload
    if the graph paused at human_approval, or None if it ran to completion."""
    interrupt_payload = None
    with st.status(t(lang, "web_progress_header"), expanded=True) as status:
        for chunk in app.stream(payload, config=config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                interrupt_payload = chunk["__interrupt__"][0].value
                break
            node_name = next(iter(chunk))
            label = t(lang, NODE_LABEL_KEYS.get(node_name, node_name))
            st.write(f"✅ {label}")
        status.update(
            label=t(lang, "web_progress_header"),
            state="complete" if interrupt_payload is None else "running",
        )
    return interrupt_payload


def advance(payload):
    try:
        interrupt_payload = run_stream(payload)
    except Exception as e:
        st.error(t(lang, "error_prefix", error=e))
        st.session_state.phase = "idle"
        return

    if interrupt_payload is not None:
        st.session_state.interrupt_payload = interrupt_payload
        st.session_state.phase = "waiting_approval"
    else:
        st.session_state.final_state = app.get_state(config).values
        st.session_state.phase = "done"
    st.rerun()


# ---------------------------------------------------------------------------
# Phase: idle — collect the topic
# ---------------------------------------------------------------------------

if st.session_state.phase == "idle":
    topic = st.text_input(t(lang, "web_topic_label"), value=st.session_state.topic)
    if st.button(t(lang, "web_run_button"), type="primary"):
        if not topic.strip():
            st.error(t(lang, "topic_empty"))
        else:
            st.session_state.topic = topic.strip()
            st.session_state.phase = "running"
            st.session_state.pending_payload = {
                "topic": st.session_state.topic,
                "iteration_count": 0,
                "citation_retry_count": 0,
                "language": lang,
            }
            st.rerun()

# ---------------------------------------------------------------------------
# Phase: running — advance the graph until interrupt or completion
# ---------------------------------------------------------------------------

elif st.session_state.phase == "running":
    st.write(t(lang, "starting_research", topic=st.session_state.topic))
    advance(st.session_state.pending_payload)

# ---------------------------------------------------------------------------
# Phase: waiting_approval — human-in-the-loop review
# ---------------------------------------------------------------------------

elif st.session_state.phase == "waiting_approval":
    payload = st.session_state.interrupt_payload

    st.subheader(t(lang, "web_review_header"))
    domain_key = DOMAIN_LABEL_KEYS.get(payload["domain"], payload["domain"])
    col1, col2 = st.columns(2)
    col1.metric(t(lang, "domain_label"), t(lang, domain_key))
    col2.metric(t(lang, "papers_count_label"), payload["papers_count"])
    st.markdown(payload["literature_summary"])

    choice_options = [
        t(lang, "web_choice_approve"),
        t(lang, "web_choice_redo_search"),
        t(lang, "web_choice_redo_directions"),
    ]
    choice_label = st.radio(t(lang, "web_choice_label"), choice_options)
    feedback = st.text_area(t(lang, "web_feedback_label"))

    if st.button(t(lang, "web_continue_button"), type="primary"):
        choice_code = str(choice_options.index(choice_label) + 1)
        st.session_state.phase = "running"
        st.session_state.pending_payload = Command(
            resume={"choice": choice_code, "feedback": feedback}
        )
        st.rerun()

# ---------------------------------------------------------------------------
# Phase: done — show the report
# ---------------------------------------------------------------------------

elif st.session_state.phase == "done":
    final_state = st.session_state.final_state

    st.subheader(t(lang, "web_report_header"))
    st.markdown(final_state["final_report"])
    st.download_button(
        t(lang, "web_download_button"),
        data=f"# {st.session_state.topic}\n\n{final_state['final_report']}",
        file_name=f"{st.session_state.topic[:50]}.md",
        mime="text/markdown",
    )

    with st.expander(t(lang, "web_papers_header")):
        for p in final_state["collected_papers"]:
            st.markdown(f"- [{p['title']}]({p['url']}) — {p['source']}")

    if st.button(t(lang, "web_new_research_button")):
        reset_session()
        st.rerun()
