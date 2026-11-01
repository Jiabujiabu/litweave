"""Offline fixed-corpus ablations, not real-model quality measurements."""
import os
import sys
os.environ['MOCK_MODE'] = '1'
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent.parent))
import argparse
import json
import time
from dataclasses import replace
from pathlib import Path
from documents import prepare_document
from evidence import retrieve, lexical_reranker
from evaluation import save_run, report_metrics, blind_export
from papers import normalize_paper
from reports import evaluate_report
from settings import Settings
from workflow import DemoEmbedder
from tests.make_pdf import make_pdf


def replay(root='.research_runs'):
    fixture = Path('tests/fixtures/original_cc0.pdf')
    if not fixture.exists():
        make_pdf(fixture)
    paper = normalize_paper({'title':'Original synthetic retrieval fixture','abstract':'Dense vectors retrieve semantic paraphrases. Hybrid retrieval combines lexical and semantic ranking.','authors':['Fixture Author'],'year':2024})
    cfg = Settings(check_claims=False, retrieval_mode='dense', fulltext=False, max_claim_revisions=0)
    variants = [('abstract_dense',cfg), ('fulltext_dense',replace(cfg,fulltext=True)),
                ('fulltext_hybrid',replace(cfg,fulltext=True,retrieval_mode='hybrid')),
                ('hybrid_rerank',replace(cfg,fulltext=True,retrieval_mode='hybrid',rerank=True)),
                ('hybrid_check',replace(cfg,fulltext=True,retrieval_mode='hybrid',check_claims=True))]
    rows = []
    for name, settings in variants:
        started = time.monotonic()
        try:
            chunks, event = prepare_document(paper,settings,fixture)
            evidence, trace, gaps = retrieve(chunks,[{'question_id':'q1','text':'Hybrid retrieval semantic paraphrases RRF'}],DemoEmbedder(),settings,lexical_reranker)
            draft = {'sections':[{'heading':'Fixture evidence','claims':[{'claim_id':'c1','text':evidence[0]['text'],'evidence_ids':[evidence[0]['evidence_id']]}]}]} if evidence else {'sections':[]}
            # Explicit stub judge only; it cannot substantiate quality or accuracy claims.
            def stub(*args):
                return {'status':'supported','reason':'scripted fixture response, not model/human judgment','contradiction':False}
            draft,issues,checks,status,revisions = evaluate_report(draft,evidence,[paper],stub,settings)
            for c in checks:
                if c.get('judgment_source') == 'model_auxiliary':
                    c['judgment_source'] = 'fixture_stub'
            rows.append({'variant':name,'mode':'offline_fixture_stub','settings':settings.to_dict(),'document':event,
                         'report_status':status,'metrics':report_metrics(draft,evidence,[paper],checks),
                         'gaps':gaps,'trace':trace,'seconds':time.monotonic()-started,'error':None})
        except Exception as error:
            rows.append({'variant':name,'mode':'offline_fixture_stub','error':type(error).__name__})
    config = {'embedding':'demo-token-hash-v1','judge':'fixture_stub','variants':[{'name':n,'settings':s.to_dict()} for n,s in variants],
              'pairs':[['abstract_dense','fulltext_dense'],['fulltext_dense','fulltext_hybrid'],['fulltext_hybrid','hybrid_rerank'],['fulltext_hybrid','hybrid_check']],
              'baseline_workflow':'docs/baseline.json (behavior probes only; no claimed quality comparison)'}
    path = save_run(config,{'paper':paper,'pdf_sha256':__import__('hashlib').sha256(fixture.read_bytes()).hexdigest()},rows,root)
    historical = Path('eval/candidates_raw_cache.json')
    if historical.exists():
        # Previously exposed topics can only generate development/history blind materials.
        count = blind_export(json.loads(historical.read_text(encoding='utf-8')),path / 'development_annotation')
        (path / 'annotation_status.json').write_text(json.dumps({'human_labels':'pending','development_rows':count,
             'heldout_candidates':'not_collected; requires separately authorized real retrieval', 'quality_results':'not_measured'}),encoding='utf-8')
    return path, rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',default='.research_runs')
    args = parser.parse_args()
    path, rows = replay(args.output)
    print(path)
    print(f"{len(rows)} fixture configurations; {sum(bool(r.get('error')) for r in rows)} errors; no measured research-quality improvement")
