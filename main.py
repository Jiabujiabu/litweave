import uuid
import os
from datetime import datetime

from langgraph.types import Command

from graph import app
from i18n import t
from ui import review_choices, status_line
from nodes import MOCK_MODE
from model_errors import ModelCallError
from model_access import local_model_session, use_model_access, user_access, PROVIDERS
from model_config_cli import configure_model
from projects import load_project, export_project
from review_cli import review_response
from pathlib import Path


def choose_language() -> str:
    print("Language / 语言:")
    print("  [1] English (default)")
    print("  [2] 中文")
    choice = input("Select 1/2 (Enter = English) / 请输入 1/2（回车默认英文）: ").strip()
    return "zh" if choice == "2" else "en"


def save_report(topic: str, report: str, lang: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic)
    filename = f"{safe_topic}_{timestamp}.md"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)

    print("\n" + t(lang, "saved_to", filename=filename))


def stream_until_interrupt(payload, config, selected_access=None):
    """Advance the graph until it either pauses at human_approval (returns the
    interrupt payload) or runs to completion (returns None). Progress
    messages are printed by the nodes themselves as they execute."""
    with (use_model_access(selected_access) if selected_access is not None else local_model_session()):
        for chunk in app.stream(payload, config=config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                return chunk["__interrupt__"][0].value
            for node_name in chunk:
                print(t(app.get_state(config).values.get("language", "en"), "node_" + node_name))
    return None


def main(project_path=None):
    lang = choose_language()
    if os.getenv('MOCK_MODE','').lower() in ('1','true'):
        print(t(lang, "web_mock_mode_warning"))
        selected_access=user_access('deepseek',PROVIDERS['deepseek']['default_model'],'',demo=True,display_name='Offline demo')
    else:
        selected_access=configure_model(lang)
        if selected_access is None:
            return

    print("=" * 50)
    print(t(lang, "app_title"))
    print("=" * 50)

    restored = load_project(Path(project_path).read_bytes()) if project_path else None
    topic = restored["topic"] if restored else input("\n" + t(lang, "ask_topic") + " ").strip()
    if not topic:
        print(t(lang, "topic_empty"))
        return

    print("\n" + t(lang, "starting_research", topic=topic) + "\n")

    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 100}
    initial_state = {
        "topic": topic,
        "iteration_count": 0,
        "citation_retry_count": 0,
        "language": lang,
    }

    try:
        payload = restored or initial_state
        while True:
            interrupt_payload = stream_until_interrupt(payload, config, selected_access)
            if interrupt_payload is None:
                break

            payload = Command(resume=review_response(interrupt_payload, app.get_state(config).values))

        final_state = app.get_state(config).values
    except ModelCallError as error:
        print(error.message(lang))
        return
    except Exception as e:
        print(f"\n❌ {t(lang, 'error_prefix', error=type(e).__name__)}")
        return

    print("\n" + "=" * 50)
    print(f"📄 {t(lang, 'report_header')}")
    print("=" * 50)
    print(status_line(final_state, lang))
    from review_workflow import render_outline
    print(render_outline(final_state,detailed=False) if final_state.get('outline') else final_state.get('final_report',''))
    print("=" * 50)

    save = input("\n" + t(lang, "save_prompt")).strip().lower()
    if save == "y":
        save_report(topic, final_state["final_report"], lang)
        target = export_project(Path(".research_runs")/(final_state.get("run_id") or config["configurable"]["thread_id"]), final_state)
        print("项目与证据导出 / Project and evidence exports:", target.resolve())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", help="Restore a local project.json; API credentials are configured separately")
    main(parser.parse_args().project)
