"""Directions after unchanged default paper selection; no paid/network calls."""
import os
os.environ['MOCK_MODE']='1'
os.environ['RESEARCH_API_DIAGNOSTICS']='.research_cache/offline_test_api_events.jsonl'
os.environ['RESEARCH_DIAGNOSTICS_CONTEXT']='offline_test'
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from langgraph.types import Command
from graph import build_graph
from model_access import user_access,use_model_access
from runtime import BudgetExceeded
from projects import project_json,load_project
from tests.test_card_coverage import corpus
import directions as d
import workflow as w
import nodes


def options(payload,count=5):
    e=payload['evidence'][0]
    return [{'direction_id':'d'+str(i),'title':'Synthetic angle '+str(i),'description':'Compare a source-reported aspect '+str(i),
        'question':'How does the source describe aspect '+str(i)+'?','search_query':'shared_query aspect '+str(i),
        'paper_ids':[e['paper_id']],'evidence_ids':[e['evidence_id']]} for i in range(count)]


class DirectionResponseValidation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state=corpus(5)
        self.state.update(selected_directions=[],selected_direction_ids=[],chunks=[])
        self.state['settings']['cache_dir']=self.temp.name

    def suggest(self,answer,state=None):
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=answer):
            return d.suggest_directions(state or self.state)

    def test_short_aliases_resolve_to_real_sources(self):
        captured=[]
        def answer(task,payload,lang):
            captured.append(payload)
            self.assertEqual(payload['papers'][0]['paper_id'],'P1')
            self.assertEqual(payload['evidence'][0]['evidence_id'],'S1')
            self.assertNotIn('chunk_id',payload['evidence'][0])
            return {'directions':options(payload)}
        result=self.suggest(answer)
        self.assertEqual(result['direction_status'],'ready')
        self.assertEqual(len(result['direction_options']),5)
        self.assertTrue(all(x['paper_ids'][0] in self.state['approved_paper_ids'] for x in result['direction_options']))
        self.assertTrue(all(x['evidence_ids'][0].startswith('de_') for x in result['direction_options']))
        self.assertEqual(result['direction_error_category'],'')

    def test_bad_citation_does_not_discard_five_valid_options(self):
        def answer(task,payload,lang):
            good=options(payload)
            bad={**good[0],'direction_id':'bad','title':'Invalid angle','evidence_ids':['S999']}
            return {'directions':good+[bad]}
        result=self.suggest(answer)
        self.assertEqual(len(result['direction_options']),5)
        self.assertEqual(result['direction_validation']['rejected'],1)
        self.assertEqual(result['direction_error_category'],'partial_validation')

    def test_paper_source_mismatch_is_rejected_per_option(self):
        def answer(task,payload,lang):
            items=options(payload)
            items[0]['paper_ids']=['P2']
            return {'directions':items}
        result=self.suggest(answer)
        self.assertEqual(len(result['direction_options']),4)
        self.assertEqual(result['direction_validation']['issues'][0]['code'],'invalid_citations')

    def test_all_bad_citations_get_actionable_reason(self):
        def answer(task,payload,lang):
            items=options(payload)
            for x in items:x['evidence_ids']=['invented']
            return {'directions':items}
        result=self.suggest(answer)
        self.assertFalse(result['direction_options'])
        self.assertEqual(result['direction_error_category'],'invalid_citations')
        self.assertIn('引用未能对应',d.failure_message(result['direction_error_category']))

    def test_structural_wrapper_and_technical_id_repairs_keep_only_grounded_options(self):
        for wrapper in (lambda items:items,lambda items:{'items':items}):
            def answer(task,payload,lang):
                items=options(payload)
                for item in items:item['direction_id']='repeated-id'
                return wrapper(items)
            result=self.suggest(answer)
            self.assertEqual(len(result['direction_options']),5)
            self.assertEqual(len({d['direction_id'] for d in result['direction_options']}),5)
            d.validate_directions(result['direction_options'],self.state,result['direction_evidence'])

    def test_empty_valid_response_is_not_a_format_or_selection_error(self):
        result=self.suggest(lambda *args:{'directions':[]})
        self.assertEqual(result['direction_error_category'],'no_supported_directions')
        self.assertEqual(result['direction_validation']['returned'],0)

    def test_json_and_budget_failures_are_distinguished(self):
        for error,expected in ((json.JSONDecodeError('fixture','',0),'invalid_json'),(BudgetExceeded('fixture'),'budget_exhausted')):
            with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=error):result=d.suggest_directions(self.state)
            self.assertEqual(result['direction_error_category'],expected)
            self.assertFalse(result['direction_options'])

    def test_no_material_makes_no_model_request(self):
        state=copy.deepcopy(self.state)
        for p in state['collected_papers']:p['abstract']=''
        with patch.object(w,'ask') as ask:result=d.suggest_directions(state)
        ask.assert_not_called()
        self.assertEqual(result['direction_error_category'],'no_readable_material')

    def test_small_context_has_its_own_reason(self):
        state=copy.deepcopy(self.state);state['settings']['context_tokens']=0
        with patch.object(w,'ask') as ask:result=d.suggest_directions(state)
        ask.assert_not_called()
        self.assertEqual(result['direction_error_category'],'context_budget')

    def test_user_uploaded_pdf_is_used_when_abstract_is_missing(self):
        state=corpus(1);state.update(chunks=[],selected_directions=[],selected_direction_ids=[])
        state['collected_papers'][0]['abstract']=''
        state['settings'].update(cache_dir=self.temp.name,fulltext=True)
        state['local_pdfs']={state['approved_paper_ids'][0]:str(Path('tests/fixtures/original_cc0.pdf').resolve())}
        with patch('documents.fetch_pdf') as fetch:
            result=self.suggest(lambda task,payload,lang:{'directions':options(payload)},state)
        fetch.assert_not_called()
        self.assertTrue(result['direction_options'])
        self.assertTrue(all(e['evidence_level']=='fulltext' for e in result['direction_evidence']))
        self.assertEqual(result['telemetry']['fulltext_attempts'],1)
        restored=load_project(project_json({**state,**result}))
        self.assertEqual(restored['resume_stage'],'directions')
        import review_workflow as review
        combined={**state,**result,'selected_directions':result['direction_options'][:1],'selected_direction_ids':[result['direction_options'][0]['direction_id']]}
        with patch.object(w,'is_mock',return_value=True),patch('documents.prepare_document') as parse:
            prepared=review.prepare_approved_evidence(combined)
        parse.assert_not_called()
        self.assertEqual(prepared['telemetry']['fulltext_attempts'],1)
        load_project(project_json({**combined,**prepared}))

    def test_retry_bypasses_valid_cache_but_preserves_old_options_on_failure(self):
        first=self.suggest(lambda task,payload,lang:{'directions':options(payload,2)})
        state={**self.state,**first,'direction_action':'retry'}
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=ConnectionError('fixture')) as ask:
            result=d.suggest_directions(state)
        ask.assert_called_once()
        self.assertEqual(result['direction_options'],first['direction_options'])
        self.assertEqual(result['direction_validation']['retained_previous'],2)
        self.assertTrue(result['direction_error'])

    def test_default_real_mode_graph_does_not_require_manual_paper_changes(self):
        seen=[]
        def create(**kwargs):
            payload=json.loads(kwargs['messages'][-1]['content']);task=payload['task']
            if task.startswith('Make a constraint'):
                result={'domain':'cs','core_constraints':['shared_query'],'questions':[{'question_id':'q1','text':'shared_query','query':'shared_query'}]}
            elif task.startswith('Judge direct'):
                result={'items':[{'paper_id':p['paper_id'],'relevant':True,'match_type':'related','reason':'synthetic connection','question_ids':['q1']} for p in payload['papers']]}
            elif task.startswith('Propose 5'):
                good=options(payload);seen.append(len(payload['papers']))
                result={'directions':good+[{**good[0],'direction_id':'bad','title':'Invalid extra','evidence_ids':['invented']}]}
            else:raise AssertionError('unexpected task')
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))],usage=None)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),close=lambda:None)
        app=build_graph();cfg={'configurable':{'thread_id':'default-choice'},'recursion_limit':100}
        with use_model_access(user_access('deepseek','deepseek-flash','fixture-not-a-real-key')),patch.object(nodes,'create_client',return_value=client),patch.object(w,'search',return_value=(self.state['collected_papers'],[])),patch.object(w,'_get_embedder',side_effect=OSError('offline')):
            app.invoke({'topic':'shared_query','settings':{'cache_dir':self.temp.name,'fulltext':False}},cfg)
            app.invoke(Command(resume={'action':'confirm'}),cfg)
        state=app.get_state(cfg).values
        self.assertEqual(len(state['approved_paper_ids']),5)
        self.assertEqual(seen,[5])
        self.assertEqual(len(state['direction_options']),5)
        self.assertEqual(app.get_state(cfg).interrupts[0].value['kind'],'directions')

    def test_frontend_explains_failure_without_blame_or_raw_code(self):
        from streamlit.testing.v1 import AppTest
        source="""import streamlit as st
from review_ui import direction_selection
st.session_state.thread_id='reason-test'
direction_selection({'directions':[],'status':'unavailable','error_category':'invalid_citations','can_retry':True,'can_search':True},{'language':'zh'})
"""
        app=AppTest.from_string(source).run()
        self.assertFalse(app.exception)
        self.assertIn('引用未能对应',app.info[0].value)
        self.assertNotIn('No grounded directions',app.info[0].value)
        self.assertFalse(app.button(key='retry_directions').disabled)


if __name__=='__main__':unittest.main()
