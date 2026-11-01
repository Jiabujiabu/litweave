"""Bilingual (English / Chinese) UI strings for the CLI and the Streamlit app.

Usage: t(lang, "key", **fmt_args) -> localized, formatted string.
`lang` is "en" or "zh"; unknown languages fall back to English.
"""

STRINGS = {
    "en": {
        "app_title": "Academic Research Agent",
        "ask_topic": "Enter your research topic:",
        "topic_empty": "Topic cannot be empty.",
        "starting_research": "Starting research on: {topic}",

        "node_decompose_directions": "Analyzing topic and classifying research domain...",
        "node_search_arxiv": "Searching arXiv...",
        "node_search_crossref": "Searching CrossRef...",
        "node_search_semantic_scholar": "Not enough papers yet — falling back to Semantic Scholar...",
        "node_process_papers": "Deduplicating and ranking retrieved papers by relevance...",
        "node_summarize_literature": "Generating literature summary...",
        "node_generate_report": "Generating final report (this can take 10-20s)...",
        "node_verify_citations": "Verifying citations against retrieved papers...",

        "searching_direction": "  -> [{source}] direction {i}/{n}: {direction}",
        "found_papers": "  found {count} paper(s) on {source}",
        "dedup_result": "  deduplicated {before} -> {after} papers",
        "rerank_result": "  embedding shortlist: {count} candidates for LLM relevance filtering",
        "filter_result": "  LLM filter kept {kept}/{shortlisted} papers as directly relevant",
        "backfill_result": "  too few papers survived filtering, backfilling {count} more from the embedding shortlist",
        "citation_check_passed": "  citation check passed -- all citations trace back to retrieved papers",
        "citation_check_retry": "  found {count} unverifiable citation(s), regenerating report (attempt {attempt})",
        "citation_check_forced": "  still {count} unverifiable citation(s) after max retries -- flagging in the report instead",
        "citation_warning_suffix": "\n\n> ⚠️ Note: the following citations could not be verified against retrieved papers and may be hallucinated: {titles}",

        "summary_header": "Literature Summary",
        "domain_label": "Domain",
        "directions_label": "Research directions",
        "papers_count_label": "Papers collected",

        "approval_title": "What would you like to do?",
        "approval_option_1": "1. Approve — generate the final report",
        "approval_option_2": "2. Redo the literature search",
        "approval_option_3": "3. Redo the direction breakdown",
        "approval_choice_input": "Enter 1/2/3: ",
        "feedback_input": "Additional comments (optional, press Enter to skip): ",
        "max_iterations_note": "Reached the max iteration limit, auto-approved.",
        "max_iterations_warning": "Max iterations (3) reached — auto-continuing to report generation.",

        "report_header": "Research Report",
        "save_prompt": "Save as .md file? (y/n): ",
        "saved_to": "Report saved to: {filename}",
        "error_prefix": "Error: {error}",

        "domain_cs": "Computer Science / STEM",
        "domain_humanities": "Humanities / Social Science",
        "domain_interdisciplinary": "Interdisciplinary",

        "web_title": "Academic Research Agent",
        "web_subtitle": "Confirm papers, trace evidence, and build an academic review outline",
        "web_language_label": "Language",
        "web_topic_label": "Research topic",
        "web_run_button": "Start research",
        "web_progress_header": "Progress",
        "web_review_header": "Review the literature summary",
        "web_choice_label": "Choose an action",
        "web_choice_approve": "Approve, generate report",
        "web_choice_redo_search": "Redo literature search",
        "web_choice_redo_directions": "Redo direction breakdown",
        "web_feedback_label": "Additional comments (optional)",
        "web_continue_button": "Continue",
        "web_report_header": "Literature review outline",
        "web_download_button": "Download report (.md)",
        "web_papers_header": "Collected papers",
        "web_new_research_button": "Start a new topic",
        "web_mock_mode_warning": "No DEEPSEEK_API_KEY configured — running in MOCK mode with placeholder LLM output.",
    },
    "zh": {
        "app_title": "学术研究智能体",
        "ask_topic": "请输入研究主题：",
        "topic_empty": "主题不能为空。",
        "starting_research": "开始研究：{topic}",

        "node_decompose_directions": "正在分析主题并判断研究领域...",
        "node_search_arxiv": "正在搜索 arXiv...",
        "node_search_crossref": "正在搜索 CrossRef...",
        "node_search_semantic_scholar": "文献数量不足，正在补充搜索 Semantic Scholar...",
        "node_process_papers": "正在对检索到的论文去重并按相关性排序...",
        "node_summarize_literature": "正在生成文献总结...",
        "node_generate_report": "正在生成最终报告（可能需要 10-20 秒）...",
        "node_verify_citations": "正在校验报告引用是否存在虚构文献...",

        "searching_direction": "  → [{source}] 方向 {i}/{n}：{direction}",
        "found_papers": "  {source} 搜到 {count} 篇论文",
        "dedup_result": "  去重：{before} → {after} 篇",
        "rerank_result": "  embedding 粗筛：{count} 篇候选进入 LLM 相关性过滤",
        "filter_result": "  LLM 过滤后保留 {kept}/{shortlisted} 篇真正相关的论文",
        "backfill_result": "  过滤后论文数不足，从 embedding 候选中补齐 {count} 篇",
        "citation_check_passed": "  引用校验通过，所有引用均可追溯到检索文献",
        "citation_check_retry": "  发现 {count} 处无法核实的引用，正在重新生成报告（第 {attempt} 次）",
        "citation_check_forced": "  已达最大重试次数，仍有 {count} 处无法核实的引用，将在报告中标注警告",
        "citation_warning_suffix": "\n\n> ⚠️ 注意：以下引用未能在检索文献中核实，可能是模型幻觉：{titles}",

        "summary_header": "文献总结",
        "domain_label": "研究领域",
        "directions_label": "研究方向",
        "papers_count_label": "已收集论文数",

        "approval_title": "请选择操作：",
        "approval_option_1": "1. 通过，生成最终报告",
        "approval_option_2": "2. 重新搜索文献",
        "approval_option_3": "3. 重新分解研究方向",
        "approval_choice_input": "请输入 1/2/3：",
        "feedback_input": "补充说明（可留空直接回车）：",
        "max_iterations_note": "已达循环上限，自动通过。",
        "max_iterations_warning": "已达最大循环次数（3次），自动继续生成报告。",

        "report_header": "调研报告",
        "save_prompt": "是否保存为 .md 文件？(y/n)：",
        "saved_to": "报告已保存至：{filename}",
        "error_prefix": "运行出错：{error}",

        "domain_cs": "理工科",
        "domain_humanities": "人文社科",
        "domain_interdisciplinary": "跨学科",

        "web_title": "学术研究智能体",
        "web_subtitle": "确认文献 → 提取可追溯证据 → 构建学术综述大纲",
        "web_language_label": "语言",
        "web_topic_label": "研究主题",
        "web_run_button": "开始研究",
        "web_progress_header": "进度",
        "web_review_header": "请审核文献总结",
        "web_choice_label": "请选择操作",
        "web_choice_approve": "通过，生成报告",
        "web_choice_redo_search": "重新搜索文献",
        "web_choice_redo_directions": "重新分解研究方向",
        "web_feedback_label": "补充说明（可选）",
        "web_continue_button": "继续",
        "web_report_header": "学术文献综述大纲",
        "web_download_button": "下载报告 (.md)",
        "web_papers_header": "已收集的论文",
        "web_new_research_button": "开始新的研究",
        "web_mock_mode_warning": "未配置 DEEPSEEK_API_KEY —— 当前以 MOCK 模式运行，LLM 输出为占位内容。",
    },
}


STRINGS["en"].update({
    "web_mock_mode_warning": "MOCK / DEMO: synthetic offline data; no network or paid model calls.",
    "node_prepare_evidence": "Preparing fulltext or abstract evidence...",
    "node_prepare_report_evidence": "Refreshing approved evidence...",
    "node_supplementary_search": "Searching for remaining evidence gaps...",
    "node_prepare_feedback": "Applying feedback and clearing previous results...",
    "accept_partial": "Accept the explicitly limited partial result",
    "end_research": "End without approval",
    "rewrite_only": "Change writing style only; reuse evidence",
    "review_limit": "Review limit reached. Accept a marked partial result or end the run.",
    "run_status": "Candidates: {candidates}; qualified: {papers}; retrieval: {status}; report: {report}",
    "local_pdf": "Optional local PDF for this paper",
    "pdf_mapping": "Optional local PDFs (paper_id=path; paper_id=path), or Enter to skip: ",
    "source_failures": "Search source events",
    "export_evidence": "Download evidence and checks (.json)",
    "not_checked_notice": "Citation identity and claim support are separate checks. Unchecked does not mean passed.",
    "max_iterations_warning": "Review limit reached; explicit user choice is required.",
    "citation_check_forced": "Citation issues remain after bounded revisions; report needs review.",
})
STRINGS["zh"].update({
    "web_mock_mode_warning": "MOCK / 演示模式：使用离线合成数据，不发起网络或付费模型调用。",
    "node_prepare_evidence": "正在解析全文或准备完整摘要证据……",
    "node_prepare_report_evidence": "正在更新已审核文献的证据……",
    "node_supplementary_search": "正在针对证据缺口补充检索……",
    "node_prepare_feedback": "正在应用反馈并清理上一轮结果……",
    "accept_partial": "接受已明确标注局限的部分结果",
    "end_research": "结束，不批准报告",
    "rewrite_only": "仅调整写作风格，复用当前证据",
    "review_limit": "已达审核轮次上限，请明确接受带局限的部分结果或结束。",
    "run_status": "候选：{candidates}；合格：{papers}；检索状态：{status}；报告状态：{report}",
    "local_pdf": "可选：上传该论文的本地 PDF",
    "pdf_mapping": "可选本地 PDF（paper_id=路径；多项用英文分号分隔），回车跳过：",
    "source_failures": "各检索来源的状态",
    "export_evidence": "下载证据与检查结果 (.json)",
    "not_checked_notice": "引用来源有效与结论得到支持是两层检查；未检查不代表通过。",
    "max_iterations_warning": "已达审核上限，必须由用户明确选择。",
    "citation_check_forced": "达到修订上限后仍有引用问题，报告保留待审核状态。",
})

STRINGS["en"].update({
    "byok_title": "Use your own model account",
    "byok_demo": "Offline demo (no API calls)",
    "byok_provider": "Provider",
    "byok_model": "Model ID",
    "byok_key": "Your API key",
    "byok_required": "Enter your API key and model in the sidebar, or select the offline demo.",
    "byok_notice": "Your key is used in this session by the app backend and selected provider. Clear it when finished.",
    "byok_clear": "Clear key and end this session's research",
})
STRINGS["zh"].update({
    "byok_title": "使用你自己的模型账户",
    "byok_demo": "离线演示（不调用 API）",
    "byok_provider": "模型服务商",
    "byok_model": "模型 ID",
    "byok_key": "你自己的 API Key",
    "byok_required": "请在侧边栏填写 API Key 和模型，或选择离线演示。",
    "byok_notice": "Key 供当前会话的后端和所选服务商使用，完成后可清除。",
    "byok_clear": "清除 Key 并结束当前会话的研究",
})

STRINGS["en"].update({
    "byok_retired": "deepseek-chat / deepseek-reasoner are retired model names. Select the current model before starting.",
    "byok_update_model": "Use deepseek-flash",
    "byok_check": "Check connection and model",
    "byok_check_ok": "Connection verified; selected model is listed. Generation can still be subject to balance, permissions or limits.",
    "byok_model_not_listed": "Connected, but the selected model is not listed. Check the model ID.",
    "byok_models": "Available models: {models}",
})
STRINGS["zh"].update({
    "byok_retired": "deepseek-chat / deepseek-reasoner 是已停用的旧模型名，请先选择当前模型。",
    "byok_update_model": "改用 deepseek-flash",
    "byok_check": "检查连接与模型",
    "byok_check_ok": "连接正常，已选模型可见；生成仍可能受余额、权限或限流影响。",
    "byok_model_not_listed": "连接正常，但模型列表不含已选模型，请核对模型 ID。",
    "byok_models": "可用模型：{models}",
})

STRINGS["en"].update({
    "byok_model_choice":"Model",
    "custom_model_id":"Custom model API ID",
    "refresh_models":"Refresh model list",
    "test_connection":"Test connection",
    "validation_fee_notice":"Test connection sends ONE real generation request with at most 64 output tokens and may incur a small API charge. It runs only when you click.",
    "generation_verified":"Real generation passed for this configuration.",
    "list_loaded_not_verified":"Model list loaded. This does not verify generation. Your selection has not changed.",
    "list_failure_nonblocking":"You can still test the configured model even if the list cannot be loaded.",
    "api_diagnostic":"Request diagnostic (redacted)",
    "validation_reply":"Test reply: {reply}",
})
STRINGS["zh"].update({
    "byok_model_choice":"选择模型",
    "custom_model_id":"自定义模型 API ID",
    "refresh_models":"刷新模型列表",
    "test_connection":"测试连接",
    "validation_fee_notice":"点击测试将发送一次最多64输出token的真实生成请求，可能产生少量API费用；仅在你点击后调用。",
    "generation_verified":"当前配置的真实生成验证已通过。",
    "list_loaded_not_verified":"模型列表已加载，不代表生成已验证；当前选择未更改。",
    "list_failure_nonblocking":"列表获取失败不影响继续测试已配置的模型。",
    "api_diagnostic":"请求诊断（已脱敏）",
    "validation_reply":"测试回复：{reply}",
})

def t(lang: str, key: str, **kwargs) -> str:
    table = STRINGS.get(lang, STRINGS["en"])
    template = table.get(key) or STRINGS["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template
