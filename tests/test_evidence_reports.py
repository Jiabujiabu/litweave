import os
os.environ['MOCK_MODE'] = '1'
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import numpy as np
from documents import prepare_document, chunks_from_pages
from evidence import retrieve, lexical_reranker
from papers import normalize_paper
from reports import evaluate_report, deterministic_checks, render_report
from settings import Settings
from test_workflow import StubEmbedder
from make_pdf import make_pdf


class SemanticStub:
    model_id = 'fixture-semantic-stub-v1'

    def encode(self, texts):
        return np.array([[float(any(x in t.lower() for x in ('car', 'automobile'))),
                          float('rrf' in t.lower()), 0.01] for t in texts])


class StageB(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = Settings(cache_dir=self.temp.name, max_claim_revisions=0)
        self.paper = normalize_paper({'title':'Original CC0 fixture', 'abstract':'Complete abstract fallback.', 'url':'https://example.org/fixture'})

    def fixture(self):
        path = Path(self.temp.name) / 'original.pdf'
        make_pdf(path)
        return path

    def test_pdf_locations_cache_and_invalidation(self):
        path = self.fixture()
        chunks, first = prepare_document(self.paper, self.cfg, path)
        self.assertEqual(first['evidence_level'], 'fulltext')
        self.assertEqual({c['page_start'] for c in chunks}, {1,2})
        self.assertTrue(any(c['is_reference'] for c in chunks))
        again, second = prepare_document(self.paper, self.cfg, path)
        self.assertEqual(chunks, again)
        self.assertTrue(second['cache_hit'])
        changed, third = prepare_document(self.paper, replace(self.cfg, chunk_tokens=20, chunk_overlap=3), path)
        self.assertFalse(third['cache_hit'])
        self.assertNotEqual([c['chunk_id'] for c in chunks], [c['chunk_id'] for c in changed])

    def test_document_fallback_and_limits(self):
        bad = Path(self.temp.name) / 'bad.pdf'
        bad.write_text('not a pdf')
        chunks, event = prepare_document(self.paper, self.cfg, bad)
        self.assertEqual(event['evidence_level'], 'abstract')
        self.assertIsNone(chunks[0]['page_start'])
        _, event = prepare_document(self.paper, replace(self.cfg,max_pages=1), self.fixture())
        self.assertEqual(event['reason'], 'page_limit_exceeded')
        p = normalize_paper({'title':'Metadata only'})
        self.assertEqual(prepare_document(p,self.cfg,allow_download=False)[0], [])

    def test_dense_hybrid_rerank_and_reference_exclusion(self):
        cs = chunks_from_pages('p1', ['automobile experiment\n\nReferences\nRRF RRF'], self.cfg)
        cs += chunks_from_pages('p2', ['RRF combines rankings using reciprocal rank fusion.'], self.cfg)
        qs = [{'question_id':'q1','text':'car','query':'car'}]
        evidence, trace, gaps = retrieve(cs,qs,SemanticStub(),replace(self.cfg,retrieval_mode='dense'))
        self.assertEqual(evidence[0]['paper_id'], 'p1')
        self.assertFalse(any(e['is_reference'] for e in evidence))
        evidence, trace, gaps = retrieve(cs,[{'question_id':'q2','text':'RRF'}],SemanticStub(),replace(self.cfg,rerank=True),lexical_reranker)
        self.assertEqual(evidence[0]['paper_id'], 'p2')
        self.assertTrue(trace[0]['rerank'])
        self.assertTrue(trace[0]['index_cache_hit'])
        self.assertEqual(retrieve(cs,qs,SemanticStub(),replace(self.cfg,context_tokens=0))[2], ['q1'])

    def example(self, ids=None):
        chunk = chunks_from_pages(self.paper['paper_id'], ['The automobile experiment used a small sample.'], self.cfg, 'abstract')[0]
        evidence = [{**chunk,'evidence_id':'e1','original_text':chunk['text']}]
        draft = {'sections':[{'heading':'Results','claims':[{'claim_id':'c1','text':'The experiment proves universal superiority.','evidence_ids':ids if ids is not None else ['e1']}]}]}
        return draft, evidence

    def test_unknown_empty_and_wrong_level(self):
        for ids in ([], ['unknown'], ['e1','e1']):
            draft, ev = self.example(ids)
            self.assertTrue(deterministic_checks(draft,ev,[self.paper]))
        draft, ev = self.example()
        draft['sections'][0]['claims'][0]['required_level'] = 'fulltext'
        self.assertTrue(deterministic_checks(draft,ev,[self.paper]))

    def test_real_citation_does_not_imply_support(self):
        draft, ev = self.example()
        for support in ('unsupported','partially_supported','insufficient_evidence'):
            judge = lambda *args: {'status':support,'reason':'sample does not establish universal conclusion','contradiction':False}
            result = evaluate_report(draft,ev,[self.paper],judge,self.cfg)
            self.assertEqual(result[3], 'needs_review')
        result = evaluate_report(draft,ev,[self.paper],lambda *a: {},self.cfg)
        self.assertEqual(result[2][0]['status'], 'not_checked')
        self.assertNotEqual(result[3], 'passed')

    def test_revision_is_revalidated_and_exhaustion_truthful(self):
        draft, ev = self.example()
        def ask(task,*args):
            if task == 'support': return {'status':'unsupported','reason':'too strong','contradiction':False}
            return {'claim_id':'c1','text':'Narrow claim','evidence_ids':['invented']}
        result = evaluate_report(draft,ev,[self.paper],ask,replace(self.cfg,max_claim_revisions=1))
        self.assertEqual(result[3], 'failed')
        self.assertEqual(result[4], {'c1':1})
        self.assertIn('unknown evidence',result[1][0]['reason'])

    def test_empty_and_disabled_and_reference_list(self):
        self.assertEqual(evaluate_report({'sections':[]},[],[],None,self.cfg)[3], 'not_applicable')
        draft, ev = self.example()
        result = evaluate_report(draft,ev,[self.paper],None,replace(self.cfg,check_claims=False))
        self.assertEqual(result[3], 'needs_review')
        unrelated = normalize_paper({'title':'Unused Paper'})
        report = render_report('topic',draft,ev,[self.paper,unrelated],result[3],result[2])
        self.assertNotIn('Unused Paper',report)
        self.assertIn('abstract; no page',report)
        self.assertIn('Original evidence',report)

    def test_graph_review_resume_end_and_feedback(self):
        from graph import build_graph
        from langgraph.types import Command
        app = build_graph()
        config = {'configurable':{'thread_id':'fixture'}, 'recursion_limit':80}
        initial = {'topic':'retrieval evidence', 'language':'zh', 'settings':{'cache_dir':self.temp.name}}
        app.invoke(initial,config)
        self.assertTrue(app.get_state(config).interrupts)
        app.invoke(Command(resume={'action':'rescope','feedback':'只看2024年'}),config)
        state = app.get_state(config).values
        self.assertEqual(state['research_plan']['year'], {'min':2024,'max':2024})
        self.assertTrue(state['run_history'])
        decisions = {p['paper_id']:{'decision':'keep','reason':'fixture inclusion'} for p in app.get_state(config).interrupts[0].value['papers']}
        app.invoke(Command(resume={'action':'confirm','decisions':decisions}),config)
        state=app.get_state(config).values
        self.assertEqual(app.get_state(config).interrupts[0].value['kind'],'directions')
        app.invoke(Command(resume={'action':'generate','selected_ids':[d['direction_id'] for d in state['direction_options']]}),config)
        self.assertEqual(app.get_state(config).interrupts[0].value['kind'],'outline')
        app.invoke(Command(resume={'action':'accept'}),config)
        state = app.get_state(config).values
        self.assertIn(state['citation_check'], ('needs_review','not_applicable'))
        self.assertIn('MOCK / DEMO',state['final_report'])
        self.assertEqual(state['telemetry']['model_calls'],0)
        self.assertEqual(state['telemetry']['requests'],0)


if __name__ == '__main__':
    unittest.main()
