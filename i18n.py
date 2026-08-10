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
        "web_subtitle": "LangGraph-powered literature research assistant",
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
        "web_report_header": "Final report",
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
        "web_subtitle": "基于 LangGraph 的文献调研助手",
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
        "web_report_header": "最终报告",
        "web_download_button": "下载报告 (.md)",
        "web_papers_header": "已收集的论文",
        "web_new_research_button": "开始新的研究",
        "web_mock_mode_warning": "未配置 DEEPSEEK_API_KEY —— 当前以 MOCK 模式运行，LLM 输出为占位内容。",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    table = STRINGS.get(lang, STRINGS["en"])
    template = table.get(key) or STRINGS["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template
