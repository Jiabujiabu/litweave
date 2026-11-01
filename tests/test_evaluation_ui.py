import os
os.environ['MOCK_MODE'] = '1'
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from evaluation import relevance_metrics, report_metrics, blind_export, save_run
from runtime import Runtime, BudgetExceeded


class Evaluation(unittest.TestCase):
    def test_denominators_provenance_and_zero(self):
        labels = [{'paper_id':'p1','label':'direct','source':'human'}, {'paper_id':'p2','label':'partial','source':'human'}, {'paper_id':'p3','label':'error','source':'none'}]
        metrics = relevance_metrics(['p1','p2','p3'],labels)
        self.assertEqual(metrics['selected_paper_relevance'], .5)
        self.assertEqual(metrics['errors'],1)
        self.assertIsNone(metrics['precision_at_k'])
        self.assertEqual(relevance_metrics(['p1'],labels[:1])['precision_at_k'], .2)
        self.assertIsNone(relevance_metrics([],[])['selected_paper_relevance'])
        self.assertIsNone(relevance_metrics(['p1'],[{'paper_id':'p1','label':'direct','source':'model'}])['selected_paper_relevance'])
        for bad in ([labels[0],labels[0]], [{'paper_id':'bad','label':'direct','source':'human'}]):
            with self.assertRaises(ValueError): relevance_metrics(['p1'],bad)

    def test_uncited_substantive_report_fails_coverage(self):
        draft = {'sections':[{'heading':'A','claims':[{'claim_id':'c','text':'Scientific assertion','evidence_ids':[]}]}]}
        metrics = report_metrics(draft,[],[],[])
        self.assertEqual(metrics['citation_integrity'],0)
        self.assertEqual(metrics['citation_coverage'],0)
        self.assertIsNone(report_metrics({'sections':[]},[],[],[])['citation_integrity'])

    def test_blind_export_no_suggestions_or_scores_and_unique_runs(self):
        with tempfile.TemporaryDirectory() as d:
            cases = [{'topic':'T','papers':[{'title':'A','doi':'10.1234/a','abstract':'full abstract','score':1,'llm_suggestion':'y'}, {'title':'A','doi':'10.1234/a'}]}]
            self.assertEqual(blind_export(cases,d),1)
            text = (Path(d)/'blind_candidates.csv').read_text(encoding='utf-8-sig')
            self.assertNotIn('suggestion',text)
            self.assertNotIn('score',text)
            first = save_run({},cases,[],root=d)
            second = save_run({},cases,[],root=d)
            self.assertNotEqual(first,second)
            self.assertEqual(json.loads((first/'snapshot.json').read_text(encoding='utf-8')),cases)

    def test_split_frozen_and_clusters_disjoint(self):
        path = Path('eval/splits.json')
        data = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),Path('eval/splits.sha256').read_text().strip())
        self.assertEqual((len(data['development']),len(data['heldout'])),(10,20))
        self.assertFalse({x['cluster'] for x in data['development']} & {x['cluster'] for x in data['heldout']})

    def test_global_budget_across_stages(self):
        r = Runtime({'settings':{'max_requests':1,'max_model_calls':1,'max_total_tokens':5000}})
        r.model([{'content':'small input'}],'fixture')
        with self.assertRaises(BudgetExceeded): r.request()
        resumed = Runtime({'settings':r.settings.to_dict(),'telemetry':r.data})
        with self.assertRaises(BudgetExceeded): resumed.model([{'content':'small'}],'fixture')

    def test_mock_real_eval_rejected(self):
        import sys
        sys.path.insert(0,str(Path('eval').resolve()))
        from run_eval import run_case
        from llm_judge import judge_chunk
        with self.assertRaises(RuntimeError): run_case({'topic':'no paid calls'})
        with self.assertRaises(RuntimeError): judge_chunk('T',[])

    def test_cli_review_continue_and_export(self):
        import main
        from graph import build_graph
        with patch.object(main,'app',build_graph()), patch('builtins.input',side_effect=['2','retrieval evidence','1','','','1','1,2','1','y']), patch.object(main,'save_report') as save, patch.object(main,'export_project'), patch('builtins.print'):
            main.main()
        self.assertTrue(save.called)
        self.assertIn('MOCK / DEMO',save.call_args.args[1])
        self.assertIn('needs_review',save.call_args.args[1])

    def test_streamlit_review_continue_export_controls(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file('streamlit_app.py',default_timeout=30).run()
        self.assertFalse(app.exception)
        app.text_input(key='research_topic_input').set_value('retrieval evidence')
        app.button(key='start_research').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['phase'],'waiting_approval')
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'papers')
        app.button(key='continue_research').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'directions')
        for control in app.checkbox:
            if control.key and control.key.startswith('direction_choice_'):
                control.check()
        app.button(key='generate_selected_outline').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'outline')
        app.button(key='accept_outline').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['phase'],'done')
        self.assertEqual(len(app.get('download_button')),4)
        self.assertIn('needs_review',app.session_state['final_state']['final_report'])


if __name__ == '__main__':
    unittest.main()
