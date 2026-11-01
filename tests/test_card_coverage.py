"""Per-paper extraction coverage and budget regressions; fake SDK, no public network."""
import os
os.environ['MOCK_MODE']='1'
os.environ['RESEARCH_API_DIAGNOSTICS']='.research_cache/offline_test_api_events.jsonl'
os.environ['RESEARCH_DIAGNOSTICS_CONTEXT']='offline_test'
import copy
import hashlib
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from papers import normalize_paper,stable_id
from documents import chunks_from_pages
from settings import Settings
from runtime import ACTIVE,Runtime,BudgetExceeded
from model_access import user_access,use_model_access
from projects import project_json,load_project
from card_inputs import allocate_card_inputs,cacheable,reason_text
from writing_support import ALL_FIELDS,empty_field,build_support,render_support
from evidence import retrieve
import nodes
import workflow as w
import review_workflow as review


def corpus(n=5):
    state={'topic':'shared_query','language':'zh','collected_papers':[],'paper_decisions':[],
        'approved_paper_ids':[],'corpus_signatures':{},'settings':{'fulltext':False},'chunks':[],
        'evidence':[],'research_plan':{'questions':[{'question_id':'q1','text':'shared_query','query':'shared_query'}]}}
    for i in range(n):
        abstract=('Study marker '+str(i)+'. Method: retrieve passages, rerank and answer. Data: synthetic set '+str(i)+'. Metric: answer accuracy. Result: an explicitly synthetic finding. ')*20
        p=normalize_paper({'title':'Coverage fixture '+str(i),'abstract':abstract,'year':2024,'url':'https://example.org/coverage-'+str(i)})
        p['relevance_status']='accepted';state['collected_papers'].append(p);state['paper_decisions'].append(p)
        state['approved_paper_ids'].append(p['paper_id']);state['corpus_signatures'][p['paper_id']]='input_'+str(i)
        state['chunks'].extend(chunks_from_pages(p['paper_id'],[abstract],Settings(),'abstract'))
    state['corpus_input_version']='inputs_fixture';state['corpus_version']='corpus_fixture'
    state['selected_directions']=[{'direction_id':'d'+str(i),'title':'Coverage '+str(i),'description':'Synthetic coverage check',
        'question':'shared_query','search_query':'shared_query','paper_ids':state['approved_paper_ids'],'evidence_ids':[]} for i in range(3)]
    state['selected_direction_ids']=[d['direction_id'] for d in state['selected_directions']]
    return state


def packed(state):
    cfg=Settings.load(state['settings'])
    inputs,chunks,alloc,_=allocate_card_inputs(state,state['chunks'],cfg)
    return {**state,'card_evidence':inputs,'chunks':chunks,'evidence':inputs,'card_allocation':alloc}


def valid_response(payload):
    result={f:{'status':'not_found_in_processed_text','text':'','evidence_ids':[]} for f in ALL_FIELDS}
    result['findings']={'status':'found','text':payload['evidence'][0]['original_text'][:90],
        'evidence_ids':[payload['evidence'][0]['evidence_id']]}
    return result


class PaperCoverage(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)

    def test_five_and_ten_long_papers_all_get_their_own_material(self):
        for n in (5,10):
            state=corpus(n)
            inputs,chunks,alloc,remaining=allocate_card_inputs(state,state['chunks'],Settings())
            self.assertEqual({e['paper_id'] for e in inputs},set(state['approved_paper_ids']))
            self.assertTrue(all(a['status']=='ready' and a['evidence_ids'] for a in alloc))
            self.assertEqual(sum(len(e['text'])+512 for e in inputs)+remaining,12000)
            table={c['chunk_id']:c for c in chunks}
            for e in inputs:
                self.assertEqual(e['content_hash'],hashlib.sha256(e['text'].encode()).hexdigest())
                self.assertEqual(e['text'],table[e['chunk_id']]['text'])

    def test_source_allocation_is_stable_across_paper_order(self):
        state=corpus(10)
        first=allocate_card_inputs(state,state['chunks'],Settings())[0]
        reverse={**state,'collected_papers':list(reversed(state['collected_papers']))}
        second=allocate_card_inputs(reverse,state['chunks'],Settings())[0]
        self.assertEqual(first,second)

    def test_legacy_top_k_can_only_represent_first_paper_but_card_inputs_cover_all(self):
        state=corpus(5);chunks=[]
        for i,p in enumerate(state['collected_papers']):
            for j in range(4):
                text=(str(i)+'_'+str(j)+' '+('shared_query '*140 if i==0 else 'unrelated_token '*140))[:1800].ljust(1800,'x')
                # Keep an exact fixed-size source so the old global context fills on repeated first-paper hits.
                c=chunks_from_pages(p['paper_id'],[text],Settings(),'abstract')[0]
                c['text']=text;c['content_hash']=hashlib.sha256(text.encode()).hexdigest();c['chunk_id']=stable_id('c_',[p['paper_id'],j,text])
                chunks.append(c)
        cfg=Settings(cache_dir=self.temp.name,top_evidence=2)
        queries=[{'question_id':'q'+str(i),'text':'shared_query','query':'shared_query'} for i in range(4)]
        old,_,_=retrieve(chunks,queries,None,cfg)
        self.assertEqual({e['paper_id'] for e in old},{state['approved_paper_ids'][0]})
        new=allocate_card_inputs(state,chunks,cfg)[0]
        self.assertEqual({e['paper_id'] for e in new},set(state['approved_paper_ids']))

    def test_preparation_no_longer_uses_topic_top_k_as_card_input(self):
        state=corpus(5);state['settings'].update(cache_dir=self.temp.name,top_evidence=1)
        with patch.object(w,'_get_embedder',side_effect=OSError('offline')),patch.object(w,'is_mock',return_value=False):
            result=review.prepare_approved_evidence(state)
        self.assertEqual({e['paper_id'] for e in result['card_evidence']},set(state['approved_paper_ids']))
        self.assertTrue(all(a['status']=='ready' for a in result['card_allocation']))

    def test_real_mode_fake_sdk_extracts_all_ten_with_existing_global_budget(self):
        state=packed(corpus(10));state['telemetry']={'reserved_tokens':30000,'model_calls':8,'requests':8}
        seen=[];parameters=[]
        def create(**kwargs):
            payload=json.loads(kwargs['messages'][-1]['content']);seen.append(payload['paper']['paper_id']);parameters.append(kwargs)
            self.assertTrue(all(e['paper_id']==payload['paper']['paper_id'] for e in payload['evidence']))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(valid_response(payload))))],usage=None)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),close=lambda:None)
        with use_model_access(user_access('deepseek','deepseek-flash','fixture-not-real-key')),patch.object(nodes,'create_client',return_value=client):
            result=review.extract_evidence_cards(state)
        self.assertEqual(set(seen),set(state['approved_paper_ids']))
        self.assertEqual(len(seen),10)
        self.assertTrue(all(c['processing_status']=='extracted' for c in result['evidence_cards']))
        self.assertEqual(result['telemetry']['model_calls'],18)
        self.assertLessEqual(result['telemetry']['reserved_tokens'],100000)
        self.assertTrue(all(p['max_tokens']==2048 for p in parameters))

    def test_budget_shortfall_is_explicit_not_all_not_extracted(self):
        state=packed(corpus(5));state['settings']['max_model_calls']=1
        count=[]
        def create(**kwargs):
            payload=json.loads(kwargs['messages'][-1]['content']);count.append(payload['paper']['paper_id'])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(valid_response(payload))))],usage=None)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),close=lambda:None)
        with use_model_access(user_access('deepseek','deepseek-flash','fixture-not-real-key')),patch.object(nodes,'create_client',return_value=client):
            result=review.extract_evidence_cards(state)
        self.assertEqual(len(count),1)
        self.assertEqual(sum(c['processing_status']=='model_budget' for c in result['evidence_cards']),4)
        state.update(result)
        node=review.skeleton(state)['nodes'][3];node['writing_support']=build_support(node,state)
        rendered='\n'.join(render_support(node,state,lambda ids:'[source]',str))
        self.assertIn('本轮模型或 token 额度不足',rendered)
        self.assertNotIn('尚未提取',rendered)

    def test_provider_failure_does_not_stop_later_papers(self):
        state=packed(corpus(5));failed=state['approved_paper_ids'][1]
        def ask(task,payload,lang):
            if payload['paper']['paper_id']==failed:raise RuntimeError('provider fixture')
            return valid_response(payload)
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=ask):result=review.extract_evidence_cards(state)
        self.assertEqual([c['processing_status'] for c in result['evidence_cards']],['extracted','provider_error','extracted','extracted','extracted'])
        self.assertNotIn(next(c['card_id'] for c in result['evidence_cards'] if c['paper_id']==failed),result['card_cache'])

    def test_first_paper_citation_cannot_be_copied_to_other_papers(self):
        state=packed(corpus(5));foreign=state['card_evidence'][0]
        def ask(task,payload,lang):
            result=valid_response(payload)
            if payload['paper']['paper_id']!=foreign['paper_id']:
                result['findings']['evidence_ids']=[foreign['evidence_id']]
            return result
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=ask):
            result=review.extract_evidence_cards(state)
        for card in result['evidence_cards']:
            if card['paper_id']!=foreign['paper_id']:
                self.assertEqual(card['fields']['findings']['status'],'not_checked')
                self.assertEqual(card['processing_status'],'invalid_response')

    def test_retry_only_calls_failed_paper_without_download_or_budget_reset(self):
        state=packed(corpus(5));failed=state['approved_paper_ids'][1]
        def ask(task,payload,lang):
            if payload['paper']['paper_id']==failed:raise RuntimeError('provider fixture')
            return valid_response(payload)
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=ask):state.update(review.extract_evidence_cards(state))
        before={c['paper_id']:copy.deepcopy(c['fields']) for c in state['evidence_cards']}
        seen=[]
        def retry(task,payload,lang):seen.append(payload['paper']['paper_id']);return valid_response(payload)
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=retry),patch('documents.prepare_document') as document:
            result=review.retry_card_extraction(state)
        document.assert_not_called()
        self.assertEqual(seen,[failed])
        self.assertTrue(all(c['processing_status']=='extracted' for c in result['evidence_cards']))
        for c in result['evidence_cards']:
            if c['paper_id']!=failed:self.assertEqual(c['fields'],before[c['paper_id']])
        self.assertEqual(result['card_retry_count'],1)
        self.assertEqual(result['telemetry']['reserved_tokens'],state['telemetry']['reserved_tokens'])

    def test_empty_cards_are_never_cacheable_even_with_a_completed_flag(self):
        bad={'processing_status':'extracted','fields':{f:empty_field() for f in ALL_FIELDS}}
        self.assertFalse(cacheable(bad))

    def test_missing_material_and_context_shortfall_are_distinct(self):
        state=corpus(3);missing=state['approved_paper_ids'][-1]
        state['collected_papers'][-1]['abstract']='';state['chunks']=[c for c in state['chunks'] if c['paper_id']!=missing]
        state['settings']['context_tokens']=0
        inputs,chunks,alloc,_=allocate_card_inputs(state,state['chunks'],Settings.load(state['settings']))
        self.assertFalse(inputs)
        self.assertEqual({a['paper_id']:a['status'] for a in alloc}[missing],'material_missing')
        self.assertEqual(sum(a['status']=='context_budget' for a in alloc),2)

    def test_inactive_papers_are_not_drawn_as_blank_comparison_rows(self):
        state=corpus(3)
        state['selected_directions'][0]['paper_ids']=state['approved_paper_ids'][:1];state['selected_directions']=state['selected_directions'][:1]
        for p in state['collected_papers'][1:]:p['evidence_level']='not_processed'
        support=build_support(review.skeleton(state)['nodes'][3],state)
        self.assertEqual(len(support['comparison_rows']),1)

    def test_task_reservation_does_not_count_unsent_deepseek_schema(self):
        from model_schemas import SCHEMAS
        access=user_access('deepseek','deepseek-flash','fixture-not-real-key');runtime=Runtime({})
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))],usage=None))),close=lambda:None)
        messages=[{'role':'user','content':'Return JSON.'}]
        with use_model_access(access),patch.object(nodes,'create_client',return_value=client):
            token=ACTIVE.set(runtime)
            try:nodes.call_llm(messages,task='card',language='en',response_schema=SCHEMAS['card'])
            finally:ACTIVE.reset(token)
        expected=len(messages[0]['content'])+32+len(json.dumps({'type':'json_object'}))+32+2048
        self.assertEqual(runtime.data['reserved_tokens'],expected)

    def test_card_inputs_roundtrip_and_tampering_rejected(self):
        state=packed(corpus(5));state['project_phase']='papers'
        restored=load_project(project_json(state))
        self.assertEqual(restored['card_evidence'],state['card_evidence'])
        data=json.loads(project_json(state));data['state']['card_evidence'][0]['original_text']='wrong source'
        with self.assertRaises(ValueError):load_project(json.dumps(data))

    def test_web_retry_runs_without_research_or_document_download(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file('streamlit_app.py',default_timeout=30).run()
        app.text_input(key='research_topic_input').set_value('retrieval evidence')
        app.button(key='start_research').click().run()
        app.button(key='continue_research').click().run()
        for c in app.checkbox:
            if c.key and c.key.startswith('direction_choice_'):c.check()
        app.button(key='generate_selected_outline').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state['interrupt_payload']['unfinished_cards'])
        with patch('documents.prepare_document') as document,patch('workflow.search') as search:
            app.button(key='retry_card_extraction').click().run()
        self.assertFalse(app.exception)
        document.assert_not_called();search.assert_not_called()
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'outline')
        app.button(key='accept_outline').click().run()
        self.assertEqual(app.session_state['final_state']['card_retry_count'],1)
        budget=app.session_state['final_state']['telemetry']['reserved_tokens']
        app.button(key='done_retry_cards').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'outline')
        app.button(key='accept_outline').click().run()
        self.assertEqual(app.session_state['final_state']['card_retry_count'],2)
        self.assertEqual(app.session_state['final_state']['telemetry']['reserved_tokens'],budget)

    def test_retry_does_not_bypass_exhausted_global_budget(self):
        state=packed(corpus(2))
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=BudgetExceeded('fixture')):
            state.update(review.extract_evidence_cards(state))
        state['telemetry']['model_calls']=30
        with patch.object(review,'interrupt',return_value={'action':'retry_extraction'}):
            result=review.review_outline(state)
        self.assertEqual(result['outline_action'],'review')
        self.assertNotIn('evidence_cards',result)

    def test_cli_can_request_targeted_retry(self):
        from review_cli import review_response
        state=corpus(2)
        with patch('builtins.input',return_value='7'),patch('builtins.print'):
            result=review_response({'kind':'outline','unfinished_cards':1},state)
        self.assertEqual(result,{'action':'retry_extraction'})


if __name__=='__main__':unittest.main()
