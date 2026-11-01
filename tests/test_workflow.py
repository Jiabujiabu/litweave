import os
os.environ["MOCK_MODE"] = "1"
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import workflow as w
from papers import normalize_paper, deduplicate
from settings import Settings
from searches import search


class StubEmbedder:
    def encode(self, texts):
        return np.array([[float('relevant' in t.lower() or 'topic' in t.lower()), 1.] for t in texts])


class StageA(unittest.TestCase):
    def test_normalization_full_abstract(self):
        p = normalize_paper({"title": "T", "abstract": "<p>" + "A" * 700 + "</p><p>Second</p>", "DOI": "https://doi.org/10.1234/ABC"})
        self.assertEqual(p["doi"], "10.1234/abc")
        self.assertIn("\n\nSecond", p["abstract"])
        self.assertGreater(len(p["abstract"]), 700)
        self.assertEqual(normalize_paper({"summary": "N/A"})["abstract_status"], "missing")

    def test_identity_and_order(self):
        records = json.loads((Path(__file__).parent / 'fixtures/papers.json').read_text())
        merged = deduplicate(records)
        self.assertEqual(merged, deduplicate(records[::-1]))
        self.assertEqual(len(merged), 3)
        self.assertEqual(max(len(p['source_records']) for p in merged), 2)
        conflict = [{"title":"Same title", "authors":["A"], "year":2024, "doi":"10.1234/a"},
                    {"title":"Same title", "authors":["B"], "year":2024, "doi":"10.1234/b"}]
        self.assertEqual(len(deduplicate(conflict)), 2)

    def test_small_shortlist_sorted(self):
        papers = [normalize_paper({"title":"other"}), normalize_paper({"title":"relevant"})]
        with patch.object(w, '_EMBEDDER', StubEmbedder()):
            ranked = w._embedding_shortlist('topic', papers, 20)
            self.assertEqual(ranked[0]['title'], 'relevant')
            self.assertEqual(ranked, w._embedding_shortlist('topic', papers[::-1], 20))

    def test_identifier_conflicts_and_related_versions(self):
        records = [{'title':'Same work','authors':['A'],'year':2024,'doi':'10.1234/a','arxiv_id':'2401.00001'},
                   {'title':'Same work','authors':['A'],'year':2024,'doi':'10.1234/a','arxiv_id':'2401.00002'}]
        papers = deduplicate(records)
        self.assertEqual(len({p['paper_id'] for p in papers}),2)
        self.assertTrue(all(p['identity_conflicts'] for p in papers))
        self.assertEqual(papers,deduplicate(records[::-1]))
        versions = deduplicate([{'title':'Related work','authors':['A'],'year':2024,'arxiv_id':'2401.00001'},
                                {'title':'Related work','authors':['A'],'year':2024,'doi':'10.1234/formal'}])
        self.assertEqual(len(versions),2)
        self.assertTrue(all(p['related_versions'] for p in versions))
        self.assertEqual(len(deduplicate([{},{}])),1)

    def test_retry_after_long_wait_is_deferred(self):
        class Response:
            status_code = 429
            headers = {'Retry-After':'120'}
        calls = []
        def get(*a,**k):
            calls.append(k)
            return Response()
        papers, events = search('CrossRef','q',Settings(),get=get,sleep=lambda _:None)
        self.assertEqual(len(calls),1)
        self.assertIn('deferred',events[0]['detail'])
        self.assertEqual(calls[0]['timeout'],20)

    def test_no_backfill_and_post_filter_supplement(self):
        from graph import is_sufficient
        papers = [normalize_paper({"title":str(i), "abstract":"test"}) for i in range(20)]
        decisions = [{**p, "relevance_status":"accepted" if i < 2 else "rejected", "question_ids":["q1"]} for i,p in enumerate(papers)]
        with patch.object(w, 'screen', return_value=decisions):
            update = w.process_papers({"topic":"test", "candidate_papers":papers})
        self.assertEqual(len(update['collected_papers']), 2)
        self.assertEqual(is_sufficient(update), 'supplementary_search')
        self.assertEqual(is_sufficient({**update, 'search_round':2}), 'summarize_literature')

    def test_filter_invalid_fails_closed(self):
        papers = [normalize_paper({"title":"T", "abstract":"A"})]
        for data in ([], [{"paper_id":"invented", "relevant":True}], {}, 'bad'):
            with patch.object(w, 'is_mock', return_value=False), patch.object(w, 'ask', return_value=data):
                self.assertEqual(w.screen('x', papers, 'en', [{'question_id':'q1'}], {})[0]['relevance_status'], 'unjudged')

    def test_review_never_auto_approves(self):
        for count in (0, 3, 8):
            with patch.object(w, 'interrupt', return_value={'choice':'2'}):
                self.assertNotEqual(w.human_approval({'iteration_count':count})['approval_status'], 'approved')
        with patch.object(w, 'interrupt', return_value={}):
            self.assertEqual(w.human_approval({})['approval_status'], 'ended')

    def test_feedback_invalidation(self):
        update = w.prepare_feedback({'topic':'x', 'evidence':[{'old':1}], 'final_report':'old', 'citation_check':'passed'})
        self.assertEqual(update['evidence'], [])
        self.assertEqual(update['citation_check'], 'not_checked')
        self.assertEqual(update['run_history'][0]['final_report'], 'old')
        self.assertEqual(w.year_constraint('topic', '只看2024年'), {'min':2024,'max':2024})

    def test_network_events_bounded(self):
        import requests
        class Response:
            status_code = 429
            headers = {'Retry-After':'bogus'}
        cfg = Settings(search_retries=1)
        papers, events = search('CrossRef','q',cfg,get=lambda *a,**k:Response(),sleep=lambda _:None)
        self.assertEqual(papers, [])
        self.assertEqual([e['status'] for e in events], ['rate_limited','rate_limited'])
        def timeout(*a,**k): raise requests.Timeout()
        self.assertEqual(search('CrossRef','q',cfg,get=timeout,sleep=lambda _:None)[1][-1]['status'], 'timeout')
        class Empty:
            status_code = 200
            def json(self): return {'message':{'items':[]}}
        self.assertEqual(search('CrossRef','q',cfg,get=lambda *a,**k:Empty())[1][0]['status'], 'empty')


if __name__ == '__main__':
    unittest.main()
