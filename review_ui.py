"""Streamlit views for the two explicit human gates."""
import copy
import hashlib
from pathlib import Path
import streamlit as st
from langgraph.types import Command
from projects import exports
from reports import safe_url
from settings import Settings


def show_exports(state, prefix="export"):
    with st.expander("保存项目与导出 / Save project and exports"):
        st.caption("project.json 可恢复审核位置与历史；恢复后仍需输入并验证自己的 Key。 / Restore history and review position; credentials are entered separately.")
        for name,data in exports(state).items():
            st.download_button(name, data=data, file_name=name, mime="application/json" if name.endswith("json") else "text/csv" if name.endswith("csv") else "text/markdown", key=prefix+name)


def paper_review(payload, state):
    st.subheader("相关文献 / Related literature")
    st.markdown(payload.get("literature_summary", ""))
    if not payload['papers']:
        st.info('暂未找到可推荐的相关文献。可以继续检索，或展开下方选项调整研究问题。 / No related papers to recommend yet; search further or adjust your question below.')
    elif len(payload['papers'])<payload.get('target',5):
        st.info(f"目前找到 {len(payload['papers'])} 篇相关文献，尚未达到 {payload.get('target',5)} 篇的目标。可以继续检索，也可以使用已有文献选择方向。 / Fewer than the target; search further or continue with available papers.")
    decisions, local_pdfs = {}, {}
    scope = st.session_state.thread_id
    for paper in payload["papers"]:
        pid = paper["paper_id"]
        old = payload.get("human_decisions", {}).get(pid, {})
        default = old.get('decision')!='exclude'
        version = (paper.get("screen_fingerprint") or "unknown") + scope
        with st.container(border=True):
            st.text(paper["title"])
            st.caption(f"{paper.get('year') or '?'} · {', '.join(paper.get('authors', [])[:3])}")
            if paper.get('relevance_reason') and paper.get('relevance_status')!='demo_unjudged':
                st.write('相关理由 / Relevance: '+paper['relevance_reason'][:500])
            for label,url in (("原文页面 / Publication", paper.get("landing_url")), ("DOI", "https://doi.org/"+paper["doi"] if paper.get("doi") else None), ("开放全文 / Open full text", paper.get("open_access_url"))):
                if safe_url(url):
                    st.link_button(label, safe_url(url))
            keep = st.checkbox('保留这篇文献 / Include this paper',value=default,key='include_'+pid+version)
            decisions[pid] = {'decision':'keep' if keep else 'exclude','reason':''}
            with st.expander('查看摘要或补充 PDF / Abstract and optional PDF'):
                st.write(paper.get('abstract') or '暂未获取到摘要。 / Abstract not available.')
                uploaded = st.file_uploader('补充本地 PDF / Add a local PDF',type=['pdf'],key='pdf_'+pid+scope)
            if uploaded:
                data = uploaded.getvalue()
                if len(data)>Settings.load(state.get("settings")).max_download_mb*1024*1024:
                    st.error("PDF 超出大小限制 / PDF too large")
                elif not data.lstrip().startswith(b"%PDF-"):
                    st.error("文件不是 PDF / Not a PDF")
                else:
                    directory = Path(Settings.load(state.get("settings")).cache_dir)/"local_uploads"
                    directory.mkdir(parents=True, exist_ok=True)
                    path = directory/(hashlib.sha256(data).hexdigest()+".pdf")
                    path.write_bytes(data)
                    local_pdfs[pid] = str(path.resolve())
    if st.button("生成可选话题与方向 / Suggest topics and directions", key="continue_research", type="primary",disabled=not any(d['decision']=='keep' for d in decisions.values())):
        return {"action":"confirm", "decisions":decisions, "local_pdfs":local_pdfs}
    if st.button('继续检索相关文献 / Find more related papers',key='search_more_papers',disabled=not payload.get('can_search')):
        return {'action':'search','decisions':decisions,'local_pdfs':local_pdfs}
    with st.expander('检索详情 / Search details'):
        plan=payload.get('research_plan',{})
        if plan.get('core_constraints'):
            st.write('研究范围 / Scope: '+'；'.join(plan['core_constraints']))
        for q in plan.get('questions',[]):
            st.write(q.get('text',''))
        st.dataframe(payload.get('search_events',[]))
    with st.expander("调整研究范围 / Change research scope"):
        feedback = st.text_area("新范围与约束 / New scope and constraints")
        st.caption("会重新筛选；旧决定保存在历史中，预算继续累计。 / Re-screen with history retained and the same budget.")
        if st.button("按新范围重检索 / Search new scope", disabled=payload.get("at_limit", False)):
            return {"action":"rescope", "feedback":feedback}
    if st.button("结束当前研究 / End research", key="end_papers"):
        return {"action":"end"}
    return None


def direction_selection(payload, state):
    st.subheader('选择综述话题与方向 / Choose review directions')
    st.caption('可多选。所选方向将整合为一份大纲。 / Select one or more directions for one integrated outline.')
    if payload.get('status')=='partial':
        st.info(f"本次保留 {len(payload.get('directions',[]))} 个有对应来源的方向，未满 5 个。可以选择已有方向，或重新生成补充。 / Available source-linked options are below the target; select them or regenerate.")
    if not payload.get('directions'):
        from directions import failure_message
        category=payload.get('error_category')
        if not category:
            error=payload.get('generation_error') or ''
            category='budget_exhausted' if 'BudgetExceeded' in error else 'invalid_json' if 'JSONDecodeError' in error else 'invalid_response' if 'ValueError' in error else 'no_readable_material' if error=='no_readable_abstracts' else 'generation_unavailable'
        st.info(failure_message(category,state.get('language','en')))
    elif payload.get('validation',{}).get('retained_previous'):
        st.info('这次重新生成未完成，已保留上一版可用方向。 / Regeneration did not complete; previous valid directions are retained.')
    elif payload.get('validation',{}).get('rejected'):
        st.caption('部分返回选项未通过格式或来源校验，已保留有效方向。 / Invalid options were excluded; valid directions are retained.')
    stats=payload.get('material_stats',{})
    if stats.get('with_material',0) and stats.get('with_material',0)<stats.get('retained',0):
        st.caption(f"本次根据 {stats['with_material']}/{stats['retained']} 篇有可读材料的文献推荐方向，其余文献可补充摘要或正文。 / Some retained papers still need readable source material.")
    pmap={p['paper_id']:p for p in payload.get('papers',[])}
    selected=[]
    version=state.get('direction_source_version','')+st.session_state.thread_id
    for d in payload.get('directions',[]):
        with st.container(border=True):
            choose=st.checkbox(d['title'],value=d['direction_id'] in payload.get('selected_ids',[]),key='direction_choice_'+version+d['direction_id'])
            st.write(d['description'])
            st.write(d['question'])
            with st.expander('支撑文献 / Supporting literature'):
                for pid in d['paper_ids']:
                    p=pmap[pid]
                    st.text(p['title'])
                    if safe_url(p.get('landing_url')):
                        st.link_button('原文 / Publication',safe_url(p['landing_url']))
            if choose:
                selected.append(d['direction_id'])
    if st.button('根据所选方向生成一份大纲 / Generate an integrated outline',key='generate_selected_outline',type='primary',disabled=not selected):
        return {'action':'generate','selected_ids':selected}
    if st.button('返回文献列表 / Back to literature',key='directions_back_papers'):
        return {'action':'papers'}
    if st.button('继续检索 / Search further',key='directions_search',disabled=not payload.get('can_search')):
        return {'action':'search'}
    if (not payload.get('directions') or payload.get('status')=='partial') and st.button('重新生成方向 / Retry directions',key='retry_directions',disabled=not payload.get('can_retry')):
        return {'action':'retry'}
    if st.button('结束并保存当前结果 / End with current results',key='end_directions'):
        return {'action':'end'}
    return None


def outline_review(payload, state):
    st.subheader("审核学术综述大纲 / Review the literature review outline")
    st.caption('每节提供文献中的具体内容和出处，可保存草稿或补充材料后继续整理。 / Each section includes source material and citations; save the draft or add material to develop it further.')
    from review_workflow import render_outline
    st.markdown(render_outline(state, detailed=False))
    if payload.get('unfinished_cards'):
        st.caption(f"有 {payload['unfinished_cards']} 篇文献可补全提取；已完成的字段和文献将复用。 / Incomplete extractions can be retried; completed results are reused.")
        if not payload.get('can_retry_extraction'):
            st.caption('本轮已没有可用的提取重试额度，可先保存当前结果。 / No extraction retry budget remains; current results can be saved.')
        if st.button('重试未完成的文献提取 / Retry incomplete extraction',key='retry_card_extraction',disabled=not payload.get('can_retry_extraction')):
            return {'action':'retry_extraction'}
    # Friendly node edits; evidence IDs remain editable in the structured editor below.
    edited = copy.deepcopy(payload["outline"])
    version = str(state.get("outline_version", 0))+"_"+st.session_state.thread_id
    with st.expander("修改标题、顺序和内容 / Edit titles, order and content"):
        for n in edited["nodes"]:
            st.write(n['title'])
            prefix = "node_"+version+"_"+n["node_id"]
            n["title"] = st.text_input("标题 / Title", value=n["title"], key=prefix+"title")
            n["order"] = int(st.number_input("顺序 / Order", value=int(n["order"]), min_value=0, key=prefix+"order"))
            n["purpose"] = st.text_area("本节目的 / Purpose", value=n["purpose"], key=prefix+"purpose")
            for i,point in enumerate(n['argument_points']):
                point['text']=st.text_area('本节观点 / Section point',value=point['text'],key=prefix+'point'+str(i))
            tasks = st.text_area("个人补充（可选，每行一项） / Personal notes (optional)", value="\n".join(n["user_writing_tasks"]) if n.get('user_edited') else '', key=prefix+"tasks")
            n["user_writing_tasks"] = [x.strip() for x in tasks.splitlines() if x.strip()]
        if st.button("保存修改并检查 / Save edits and check", key="apply_outline_edits", disabled=payload.get("at_limit", False)):
            return {"action":"edit", "outline":edited}
    st.subheader("证据缺口 / Evidence gaps")
    for gap in payload.get("gaps", []):
        st.write(gap["description"])
    proposals = {g["gap_id"]:g for g in payload.get("gaps", []) if g.get("action")=="search"}
    selected = st.multiselect("选择要补检索的缺口 / Select gaps to search", list(proposals), format_func=lambda gid:proposals[gid].get("query", gid), key="gap_selection_"+version)
    if st.button("按所选缺口补检索 / Search selected gaps", key="supplement_search", disabled=not payload.get("can_search") or not selected):
        return {"action":"search", "gap_ids":selected}
    if st.button("返回文献审核／补充 PDF / Review corpus or add PDFs", key="back_to_papers"):
        return {"action":"papers"}
    if st.button('重新选择话题与方向 / Change selected directions',key='back_to_directions'):
        return {'action':'directions'}
    st.caption("请先保存上面的编辑，再接受当前版本。 / Save edits above before accepting the current version.")
    if st.button("接受当前大纲（含已显示缺口） / Accept current outline with displayed gaps", key="accept_outline", type="primary"):
        return {"action":"accept"}
    if st.button("结束并保留当前草稿 / End and keep current draft", key="end_outline"):
        return {"action":"end"}
    return None


def render_review(payload, state, ready=True):
    if state.get("restored_project"):
        st.caption("已恢复本地项目。显示的既有判断来自保存记录；恢复本身不重新验证研究结论。 / Restored judgments come from the saved project, not a new verification.")
    if payload.get("review_error"):
        st.error(payload["review_error"])
    show_exports(state, "review_export_")
    if not ready:
        st.info("请先配置自己的 API Key。 / Configure your API key first.")
        return
    renderer={'outline':outline_review,'directions':direction_selection,'papers':paper_review}.get(payload.get('kind'),paper_review)
    response = renderer(payload, state)
    if response:
        st.session_state.phase = "running"
        st.session_state.pending_payload = Command(resume=response)
        st.rerun()
