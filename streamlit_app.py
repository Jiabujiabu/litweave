import uuid
import os
import json
import hashlib
from pathlib import Path

import streamlit as st
from langgraph.types import Command

from graph import app
from i18n import t
from model_access import PROVIDERS, user_access, use_model_access, CredentialsRequired, retired_model
from model_errors import ModelCallError
from connection_check import refresh_models, verify_generation
from model_registry import model_options, CUSTOM_MODEL, provider_config
from ui import review_choices, status_line
from settings import Settings
from projects import load_project
from review_ui import render_review, show_exports

st.set_page_config(page_title="Academic Research Agent", page_icon="📖")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

initial_provider=st.session_state.get("byok_provider","deepseek")
initial_model=st.session_state.get("selected_model_id") or st.session_state.get("byok_model") or provider_config(initial_provider)["default_model"]
initial_options=model_options(initial_provider)
initial_choice=initial_model if initial_model in initial_options else CUSTOM_MODEL

defaults = {
    "language": "en",
    "phase": "idle",          # idle -> running -> waiting_approval <-> running -> done
    "thread_id": str(uuid.uuid4()),
    "topic": "",
    "pending_payload": None,  # dict (initial state) or Command(resume=...)
    "interrupt_payload": None,
    "final_state": None,
    "byok_provider": "deepseek",
    "byok_model": PROVIDERS["deepseek"]["default_model"],
    "byok_api_key": "",
    "connection_result": None,
    "model_list_result": None,
    "remote_models": {},
    "byok_model_choice": initial_choice,
    "byok_custom_id": initial_model if initial_choice==CUSTOM_MODEL else "",
    "selected_model_id": initial_model,
    "selected_model_display": initial_options.get(initial_model,initial_model),
    "byok_demo": os.getenv("MOCK_MODE", "").lower() in ("1", "true"),
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Keep unsaved review controls across the two gates and the intervening progress view.
# Streamlit otherwise removes values of widgets that temporarily disappear.
for key in list(st.session_state):
    if key.startswith(("decision_", "include_", "direction_choice_", "reason_", "node_", "outline_json_", "gap_selection_")):
        st.session_state[key] = st.session_state[key]


def reset_session():
    st.session_state.phase = "idle"
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.topic = ""
    st.session_state.pending_payload = None
    st.session_state.interrupt_payload = None
    st.session_state.final_state = None


def clear_connection_result():
    st.session_state.connection_result = None
    st.session_state.last_api_error = None


def change_provider():
    st.session_state.byok_api_key = ""
    st.session_state.byok_model_choice = provider_config(st.session_state.byok_provider)["default_model"]
    st.session_state.byok_custom_id = ""
    st.session_state.model_list_result = None
    clear_connection_result()


def change_key():
    st.session_state.remote_models.pop(st.session_state.byok_provider, None)
    st.session_state.model_list_result = None
    clear_connection_result()


def clear_user_credentials():
    st.session_state.byok_api_key = ""
    change_key()
    reset_session()


def current_web_access():
    return user_access(st.session_state.byok_provider, st.session_state.selected_model_id,
                       st.session_state.byok_api_key, demo=st.session_state.byok_demo,
                       display_name=st.session_state.selected_model_display)


def render_api_failure(result):
    diagnostic=result.get("diagnostic") or {}
    category=result.get("category") or diagnostic.get("category") or "unknown"
    st.error(ModelCallError(category,provider=diagnostic.get("provider"),status=diagnostic.get("http_status"),parameter=diagnostic.get("parameter")).message(lang))
    if diagnostic:
        with st.expander(t(lang,"api_diagnostic")):
            st.json(diagnostic)


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

with st.sidebar:
    locked = st.session_state.phase != "idle"
    st.subheader(t(lang, "byok_title"))
    st.checkbox(t(lang, "byok_demo"), key="byok_demo", disabled=locked, on_change=clear_connection_result)
    st.selectbox(t(lang, "byok_provider"), list(PROVIDERS), key="byok_provider",
                 format_func=lambda value: PROVIDERS[value]["label"], on_change=change_provider,
                 disabled=locked or st.session_state.byok_demo)
    options=model_options(st.session_state.byok_provider,st.session_state.remote_models.get(st.session_state.byok_provider),
                          st.session_state.byok_model_choice)
    st.selectbox(t(lang,"byok_model_choice"),list(options),key="byok_model_choice",format_func=options.get,
                 disabled=locked or st.session_state.byok_demo,on_change=clear_connection_result)
    if st.session_state.byok_model_choice==CUSTOM_MODEL:
        st.text_input(t(lang,"custom_model_id"),key="byok_custom_id",disabled=locked or st.session_state.byok_demo,on_change=clear_connection_result)
        model_id=st.session_state.byok_custom_id.strip()
        display_name="Custom: "+model_id
    else:
        model_id=st.session_state.byok_model_choice
        display_name=options[model_id]
    st.session_state.selected_model_id=model_id
    st.session_state.selected_model_display=display_name
    st.caption("API ID: "+model_id)
    st.text_input(t(lang, "byok_key"), type="password", key="byok_api_key",
                  disabled=locked or st.session_state.byok_demo, on_change=change_key)
    st.caption(t(lang, "byok_notice"))
    st.button(t(lang, "byok_clear"), key="byok_clear", on_click=clear_user_credentials,
              disabled=st.session_state.phase == "running")

try:
    access=current_web_access()
    access_ready=True
except CredentialsRequired:
    access=None
    access_ready=False

with st.sidebar:
    if st.button(t(lang,"refresh_models"),key="refresh_models",disabled=locked or not access_ready or st.session_state.byok_demo):
        try:
            listing=refresh_models(access)
            st.session_state.model_list_result=listing
            st.session_state.remote_models[access.provider]=listing.get("model_records",[])
        except ModelCallError as error:
            st.session_state.model_list_result={"status":"failed","category":error.category,"diagnostic":error.diagnostic}
        st.rerun()
    listing=st.session_state.model_list_result
    if listing:
        if listing.get("status")=="failed":
            render_api_failure(listing)
            st.caption(t(lang,"list_failure_nonblocking"))
        else:
            st.info(t(lang,"list_loaded_not_verified"))
    st.caption(t(lang,"validation_fee_notice"))
    if st.button(t(lang,"test_connection"),key="check_connection",disabled=locked or not access_ready or st.session_state.byok_demo):
        st.session_state.connection_result=verify_generation(current_web_access(),consent=True,output_limit=64)
    result=st.session_state.connection_result
    if result:
        if result.get("generation_verified"):
            st.success(t(lang,"generation_verified"))
            st.caption(t(lang,"validation_reply",reply=result.get("response_preview","")))
            with st.expander(t(lang,"api_diagnostic")):
                st.json(result.get("diagnostic"))
        else:
            render_api_failure(result)

if st.session_state.byok_demo:
    st.warning(t(lang,"web_mock_mode_warning"))
elif not access_ready:
    st.info(t(lang,"byok_required"))

validated=bool(st.session_state.connection_result and st.session_state.connection_result.get("generation_verified"))
access_ready=access_ready and (st.session_state.byok_demo or validated)

st.title(t(lang, "web_title"))
st.caption(t(lang, "web_subtitle"))

config = {"configurable": {"thread_id": st.session_state.thread_id}, "recursion_limit": 100}

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
WORKFLOW_LABELS = {
    "review_papers":"文献采用集合已确认 / Corpus decisions recorded",
    "freeze_corpus":"已记录采用集合版本 / Corpus version recorded",
    "prepare_approved_evidence":"已处理采用文献 / Approved documents processed",
    "extract_evidence_cards":"已提取逐篇证据卡片 / Evidence cards extracted",
    "generate_outline":"已生成综述大纲草稿 / Review outline drafted",
    "check_outline":"已检查论点与引用 / Arguments and citations checked",
    "review_outline":"已记录大纲审核决定 / Outline decision recorded",
    "supplementary_search":"已完成用户触发的补检索 / Requested supplementary search completed",
    'suggest_directions':'已归纳可选话题与方向 / Review directions suggested',
    'select_directions':'已记录所选方向 / Direction selection recorded',
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
        with use_model_access(current_web_access()):
            for chunk in app.stream(payload, config=config, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    interrupt_payload = chunk["__interrupt__"][0].value
                    break
                node_name = next(iter(chunk))
                label = WORKFLOW_LABELS.get(node_name) or t(lang, NODE_LABEL_KEYS.get(node_name, "node_" + node_name))
                st.write(f"✅ {label}")
        status.update(
            label=t(lang, "web_progress_header"),
            state="complete" if interrupt_payload is None else "running",
        )
    return interrupt_payload


def advance(payload):
    try:
        interrupt_payload = run_stream(payload)
    except ModelCallError as error:
        render_api_failure({"category":error.category,"diagnostic":error.diagnostic})
        st.session_state.phase = "idle"
        return
    except Exception as error:
        st.error(t(lang, "error_prefix", error=type(error).__name__))
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

phase_root = st.empty()
with phase_root.container():
    if st.session_state.phase == "idle":
        project_file = st.file_uploader("恢复本地项目 / Restore a local project", type=["json"], key="restore_project_file")
        if st.button("打开项目 / Open project", key="restore_project", disabled=not access_ready or project_file is None):
            try:
                restored = load_project(project_file.getvalue())
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.topic = restored["topic"]
                st.session_state.pending_payload = restored
                st.session_state.phase = "running"
                st.rerun()
            except (ValueError, TypeError, KeyError):
                st.error("无法读取项目：格式、文献集合或证据引用无效。 / Invalid project format, corpus or evidence references.")
        topic = st.text_input(t(lang, "web_topic_label"), value=st.session_state.topic, key="research_topic_input")
        if st.button(t(lang, "web_run_button"), type="primary", key="start_research", disabled=not access_ready) and access_ready:
            if not topic.strip():
                st.error(t(lang, "topic_empty"))
            else:
                st.session_state.thread_id = str(uuid.uuid4())
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
        render_review(payload, app.get_state(config).values, access_ready)

    # ---------------------------------------------------------------------------
    # Phase: done — show the report
    # ---------------------------------------------------------------------------

    elif st.session_state.phase == "done":
        final_state = st.session_state.final_state

        st.subheader(t(lang, "web_report_header"))
        from review_workflow import render_outline
        st.markdown(render_outline(final_state,detailed=False) if final_state.get('outline') else final_state.get('final_report',''))
        from card_inputs import retryable_ids,can_retry
        if final_state.get('outline') and retryable_ids(final_state):
            retry_available=can_retry(final_state,Settings.load(final_state.get('settings')))
            if not retry_available:
                st.caption('本轮已没有可用的提取重试额度，可先保存当前结果。 / No extraction retry budget remains; current results can be saved.')
            if st.button('重试未完成的文献提取 / Retry incomplete extraction',key='done_retry_cards',disabled=not access_ready or not retry_available):
                resumed=dict(final_state)
                resumed.update(resume_stage='retry_cards',project_phase='outline',review_error='')
                st.session_state.thread_id=str(uuid.uuid4())
                st.session_state.phase='running'
                st.session_state.pending_payload=resumed
                st.rerun()
        show_exports(final_state, "final_export_")

        with st.expander(t(lang, "web_papers_header")):
            from reports import safe_url
            for p in final_state.get("collected_papers", []):
                st.text(p["title"])
                if safe_url(p.get("landing_url")):
                    st.link_button("原文 / Publication", safe_url(p["landing_url"]))

        if st.button(t(lang, "web_new_research_button"), key="new_research"):
            reset_session()
            st.rerun()
