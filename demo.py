"""Three reproducible offline workflows. Never uses .env keys or public APIs."""
import argparse
import os
os.environ['MOCK_MODE'] = '1'
import json
import tempfile
from pathlib import Path
from langgraph.types import Command
from papers import normalize_paper
from graph import build_graph
from tests.make_pdf import make_pdf


def run_demo(scenario, output=None):
    state = {'topic':'retrieval evidence', 'language':'zh', 'settings':{'cache_dir':'.research_cache','min_papers':1}}
    if scenario == 'insufficient':
        state['settings'].update(min_papers=5,context_tokens=0)
    app = build_graph()
    config = {'configurable':{'thread_id':scenario}, 'recursion_limit':100}
    app.invoke(state,config)
    candidates = app.get_state(config).interrupts[0].value['papers']
    response = {'action':'confirm', 'decision_source':'fixture_simulated_human',
                'decisions':{p['paper_id']:{'decision':'keep','reason':'simulated inclusion in offline fixture'} for p in candidates}}
    if scenario == 'fulltext':
        papers = app.get_state(config).values['collected_papers']
        fixture = Path(__file__).parent / 'tests/fixtures/original_cc0.pdf'
        if not fixture.exists():
            make_pdf(fixture)
        response['local_pdfs'] = {p['paper_id']:str(fixture) for p in papers[:1]}
    app.invoke(Command(resume=response),config)
    options=app.get_state(config).values.get('direction_options',[])
    if options:
        app.invoke(Command(resume={'action':'generate','selected_ids':[d['direction_id'] for d in options[:2]]}),config)
        app.invoke(Command(resume={'action':'accept'}),config)
    else:
        app.invoke(Command(resume={'action':'end'}),config)
    final = app.get_state(config).values
    if output:
        target = Path(output)
        target.mkdir(parents=True,exist_ok=True)
        (target / (scenario + '.md')).write_text(final['final_report'],encoding='utf-8')
        (target / (scenario + '.json')).write_text(json.dumps({k:final.get(k) for k in ('run_id','settings','citation_check','evidence','claim_checks','document_events','retrieval_trace','telemetry')},ensure_ascii=False,indent=2),encoding='utf-8')
        from projects import export_project
        export_project(target/scenario, final)
    return final


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario',choices=['fulltext','abstract','insufficient'],default='abstract')
    parser.add_argument('--output',default='.research_runs/demos')
    args = parser.parse_args()
    result = run_demo(args.scenario,args.output)
    print(args.scenario, result['citation_check'], result['retrieval_status'])
