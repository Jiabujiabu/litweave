import uuid
from datetime import datetime

from langgraph.types import Command

from graph import app
from i18n import t


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
        f.write(f"# {topic}\n\n")
        f.write(report)

    print("\n" + t(lang, "saved_to", filename=filename))


def stream_until_interrupt(payload, config):
    """Advance the graph until it either pauses at human_approval (returns the
    interrupt payload) or runs to completion (returns None). Progress
    messages are printed by the nodes themselves as they execute."""
    for chunk in app.stream(payload, config=config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            return chunk["__interrupt__"][0].value
    return None


def main():
    lang = choose_language()

    print("=" * 50)
    print(t(lang, "app_title"))
    print("=" * 50)

    topic = input("\n" + t(lang, "ask_topic") + " ").strip()
    if not topic:
        print(t(lang, "topic_empty"))
        return

    print("\n" + t(lang, "starting_research", topic=topic) + "\n")

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    initial_state = {
        "topic": topic,
        "iteration_count": 0,
        "citation_retry_count": 0,
        "language": lang,
    }

    try:
        payload = initial_state
        while True:
            interrupt_payload = stream_until_interrupt(payload, config)
            if interrupt_payload is None:
                break

            print("\n" + "=" * 50)
            print(f"📚 {t(lang, 'summary_header')}")
            print("=" * 50)
            print(interrupt_payload["literature_summary"])
            print("=" * 50 + "\n")

            print(t(lang, "approval_title"))
            print(t(lang, "approval_option_1"))
            print(t(lang, "approval_option_2"))
            print(t(lang, "approval_option_3"))
            choice = input(t(lang, "approval_choice_input")).strip()
            feedback = input(t(lang, "feedback_input")).strip()

            payload = Command(resume={"choice": choice, "feedback": feedback})

        final_state = app.get_state(config).values
    except Exception as e:
        print(f"\n❌ {t(lang, 'error_prefix', error=e)}")
        raise

    print("\n" + "=" * 50)
    print(f"📄 {t(lang, 'report_header')}")
    print("=" * 50)
    print(final_state["final_report"])
    print("=" * 50)

    save = input("\n" + t(lang, "save_prompt")).strip().lower()
    if save == "y":
        save_report(topic, final_state["final_report"], lang)


if __name__ == "__main__":
    main()
