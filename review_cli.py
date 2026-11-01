"""Numbered, explicit decisions for both human gates."""
import json
from pathlib import Path
from projects import save_project


def paper_decisions(payload):
    print(payload.get("literature_summary", ""))
    decisions = {}
    for index,p in enumerate(payload["papers"], 1):
        print(f"\n[{index}] {p['title']} ({p.get('year') or '?'}) / {p['paper_id']}")
        print('相关理由 / Relevance:', p.get('relevance_reason',''))
        print("URL:", p.get("landing_url") or "unavailable", "DOI:", p.get("doi"), "Open full text:", p.get("open_access_url"))
        previous = payload.get("human_decisions", {}).get(p["paper_id"], {})
    edits=input('输入要移除的编号；用 +编号 恢复（逗号分隔，回车保留当前选择） / Remove numbers or +number to restore: ').strip().split(',')
    decisions={p['paper_id']:{'decision':'exclude' if payload.get('human_decisions',{}).get(p['paper_id'],{}).get('decision')=='exclude' else 'keep','reason':''} for p in payload['papers']}
    for value in edits:
        value=value.strip()
        number=value.lstrip('+')
        if number.isdigit() and 0<int(number)<=len(payload['papers']):
            decisions[payload['papers'][int(number)-1]['paper_id']]['decision']='keep' if value.startswith('+') else 'exclude'
    mapping = input("可选 PDF：paper_id=path;... / Optional PDF mapping: ").strip()
    local = {}
    for pair in mapping.split(";"):
        if "=" in pair:
            pid,path = pair.split("=", 1)
            local[pid.strip()] = path.strip().strip('"')
    return {"action":"confirm", "decisions":decisions, "local_pdfs":local}


def review_response(payload, state):
    if payload.get("review_error"):
        print(payload["review_error"])
    while True:
        if payload.get('kind')=='directions':
            for i,d in enumerate(payload.get('directions',[]),1):
                print(f"[{i}] {d['title']} — {d['description']}")
                print(d['question'])
                papers={p['paper_id']:p for p in payload.get('papers',[])}
                print('支撑文献 / Sources:', '; '.join(papers[pid]['title'] for pid in d['paper_ids']))
            print('[1]多选方向并生成大纲 Generate [2]返回文献 Papers [3]继续检索 Search [4]结束 End [5]重试方向 Retry [6]保存 Save')
            choice=input('选择 / Select: ').strip()
            if choice=='1':
                values=input('方向编号（逗号分隔） / Direction numbers: ').strip().split(',')
                options=payload.get('directions',[])
                return {'action':'generate','selected_ids':[options[int(v)-1]['direction_id'] for v in values if v.isdigit() and 0<int(v)<=len(options)]}
            if choice in ('2','3','4','5'):
                return {'action':{'2':'papers','3':'search','4':'end','5':'retry'}[choice]}
        elif payload.get("kind")=="outline":
            from review_workflow import render_outline
            print(render_outline(state,detailed=False))
            print("[1]接受当前大纲 Accept [2]补检索 Search gaps [3]返回文献/PDF Papers [4]结束 End [5]读取编辑后的大纲 JSON Edit [6]保存项目 Save")
            if payload.get('unfinished_cards'):print('[7]重试未完成的文献提取 / Retry incomplete extraction')
            choice = input("选择 / Select: ").strip()
            if choice in ("1", "4"):
                return {"action":"accept" if choice=="1" else "end"}
            if choice=="2":
                gaps = [g for g in payload.get("gaps", []) if g.get("action")=="search"]
                for i,g in enumerate(gaps, 1):
                    print(f"[{i}] {g['description']} -> {g['query']}")
                values = input("选择缺口编号，逗号分隔 / Gap numbers: ").strip().split(",")
                return {"action":"search", "gap_ids":[gaps[int(v)-1]["gap_id"] for v in values if v.isdigit() and 0<int(v)<=len(gaps)]}
            if choice=="3":
                return {"action":"papers"}
            if choice=='7':
                return {'action':'retry_extraction'}
            if choice=="5":
                try:
                    path = input("编辑后的 outline JSON 文件路径 / Edited outline JSON path: ").strip().strip('"')
                    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
                    # project.json can be copied and its state.outline edited directly.
                    if isinstance(data,dict) and isinstance(data.get("state"),dict):
                        data = data["state"].get("outline")
                    return {"action":"edit", "outline":data}
                except (OSError, ValueError):
                    print("无法读取 JSON；当前大纲保留。 / Cannot read JSON; current outline retained.")
        else:
            print("[1]使用相关文献生成方向 Directions [2]调整问题 New scope [3]继续检索 Search [4]结束 End [6]保存项目 Save")
            choice = input("选择 / Select: ").strip()
            if choice=="1":
                return paper_decisions(payload)
            if choice=="2":
                return {"action":"rescope", "feedback":input("新范围 / New scope: ").strip()}
            if choice=="4":
                return {"action":"end"}
            if choice=='3':
                return {'action':'search'}
        if choice=="6":
            path = input("保存位置 / Project path: ").strip().strip('"')
            if path:
                save_project(path, state, payload.get('kind','papers'))
                print("已保存 / Saved")
