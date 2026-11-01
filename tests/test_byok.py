"""No real keys, SDK requests, public network or model weights are used."""
import os
os.environ['MOCK_MODE'] = '1'
os.environ['RESEARCH_API_DIAGNOSTICS'] = '.research_cache/offline_test_api_events.jsonl'
os.environ['RESEARCH_DIAGNOSTICS_CONTEXT'] = 'offline_test'
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from model_access import (user_access, use_model_access, current_access,
                          model_identity, CredentialsRequired)
from runtime import ACTIVE, Runtime
import nodes


@contextmanager
def call_context(key, provider='deepseek', model='fixture-model'):
    with use_model_access(user_access(provider,model,key)):
        token = ACTIVE.set(Runtime({}))
        try:
            yield
        finally:
            ACTIVE.reset(token)


def fake_client(content='fixture response', error=None):
    def create(**kwargs):
        if error:
            raise error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),close=lambda:None)


class BringYourOwnKey(unittest.TestCase):
    def test_missing_user_key_never_uses_server_key(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fixture-operator-key'}), patch.object(nodes,'create_client') as factory:
            with self.assertRaises(CredentialsRequired):
                user_access('deepseek','fixture-model','')
            with patch.object(nodes,'MOCK_MODE',False):
                with self.assertRaises(CredentialsRequired):
                    nodes.call_llm([{'role':'user','content':'x'}],task='plan',language='en')
            factory.assert_not_called()

    def test_explicit_user_key_and_failure_never_fall_back(self):
        seen = []
        def factory(access,timeout):
            seen.append((access.provider,access.model,access.api_key))
            return fake_client()
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fixture-operator-key'}),patch.object(nodes,'create_client',side_effect=factory):
            with call_context('fixture-user-key'):
                self.assertEqual(nodes.call_llm([{'role':'user','content':'x'}],task='plan',language='en'),'fixture response')
        self.assertEqual(seen,[('deepseek','fixture-model','fixture-user-key')])
        with call_context('fixture-user-key'), patch.object(nodes,'create_client',return_value=fake_client(error=RuntimeError('key=fixture-user-key'))) as factory:
            with self.assertRaises(nodes.ModelCallError) as error:
                nodes.call_llm([{'role':'user','content':'x'}],task='plan',language='en')
            self.assertNotIn('fixture-user-key',str(error.exception))
            self.assertEqual(factory.call_count,1)

    def test_parallel_sessions_and_context_cleanup(self):
        def factory(access,timeout):
            return fake_client(access.api_key)
        def run(key):
            with call_context(key):
                response = nodes.call_llm([{'role':'user','content':'x'}],task='plan',language='en')
            self.assertIsNone(current_access())
            return response
        with patch.object(nodes,'create_client',side_effect=factory),ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(run,['fixture-user-a','fixture-user-b'])),['fixture-user-a','fixture-user-b'])
        self.assertIsNone(current_access())
        access=user_access('deepseek','fixture-model','fixture-hidden-key')
        self.assertNotIn('fixture-hidden-key',repr(access))
        try:
            with use_model_access(access):
                raise RuntimeError('fixture')
        except RuntimeError:
            pass
        self.assertIsNone(current_access())

    def test_demo_never_initializes_paid_client(self):
        access=user_access('deepseek','fixture-model','',demo=True)
        with use_model_access(access),patch.object(nodes,'create_client') as factory:
            self.assertTrue(nodes.in_demo_mode())
            self.assertIn('MOCK',nodes.call_llm([],task='report',language='en'))
            factory.assert_not_called()

    def test_actual_sdk_requests_ignore_operator_auth_headers_and_endpoints(self):
        import httpx
        captured=[]
        def handler(request):
            captured.append(request)
            if request.url.host=='api.anthropic.com':
                return httpx.Response(200,json={'id':'msg-fixture','type':'message','role':'assistant','model':'fixture-model',
                    'content':[{'type':'text','text':'fixture'}],'stop_reason':'end_turn','stop_sequence':None,'usage':{'input_tokens':1,'output_tokens':1}})
            return httpx.Response(200,json={'id':'chatcmpl-fixture','object':'chat.completion','created':0,'model':'fixture-model',
                'choices':[{'index':0,'message':{'role':'assistant','content':'fixture'},'finish_reason':'stop'}]})
        env={'OPENAI_API_KEY':'operator-secret','OPENAI_ADMIN_KEY':'operator-admin','OPENAI_ORG_ID':'operator-org',
             'OPENAI_PROJECT_ID':'operator-project','OPENAI_BASE_URL':'https://operator.invalid',
             'OPENAI_CUSTOM_HEADERS':'Authorization: Bearer operator-secret\nauthorization: Bearer operator-lower\nOpenAI-Project: operator-project\nX-Private: operator-secret',
             'ANTHROPIC_API_KEY':'operator-secret','ANTHROPIC_AUTH_TOKEN':'operator-token','ANTHROPIC_BASE_URL':'https://operator.invalid',
             'ANTHROPIC_CUSTOM_HEADERS':'X-Api-Key: operator-secret\nx-api-key: operator-lower\nAuthorization: Bearer operator-token\nX-Private: operator-secret'}
        with patch.dict(os.environ,env):
            for provider in ('deepseek','openai','anthropic'):
                transport=httpx.Client(transport=httpx.MockTransport(handler))
                client=nodes.create_client(user_access(provider,'fixture-model','fixture-sdk-user-key'),20,transport)
                try:
                    if provider=='anthropic':
                        client.messages.create(model='fixture-model',max_tokens=8,messages=[{'role':'user','content':'fixture'}])
                    else:
                        client.chat.completions.create(model='fixture-model',messages=[{'role':'user','content':'fixture'}])
                finally:
                    client.close()
        self.assertEqual([r.url.host for r in captured],['api.deepseek.com','api.openai.com','api.anthropic.com'])
        for request in captured:
            self.assertNotIn('operator-',str(request.headers))
            if request.url.host=='api.anthropic.com':
                self.assertEqual(request.headers['x-api-key'],'fixture-sdk-user-key')
                self.assertNotIn('authorization',request.headers)
            else:
                self.assertEqual(request.headers['authorization'],'Bearer fixture-sdk-user-key')
                self.assertNotIn('openai-project',request.headers)

    def test_graph_context_resume_and_no_key_in_checkpoint(self):
        from graph import build_graph
        from langgraph.types import Command
        from papers import normalize_paper
        import workflow as w
        paper=normalize_paper({'title':'Fixture retrieval paper','abstract':'An original fixture about retrieval evidence and ranking methods.','year':2024})
        requests=[]
        def factory(access,timeout):
            self.assertEqual(access.api_key,'fixture-session-only-key')
            requests.append(access.provider)
            def create(**kwargs):
                payload=json.loads(kwargs['messages'][-1]['content'])
                task=payload['task']
                if task.startswith('Make a constraint'):
                    result={'domain':'cs','core_constraints':['retrieval'],'questions':[{'question_id':'q1','text':'retrieval','query':'retrieval'}]}
                elif task.startswith('Judge direct'):
                    result=[{'paper_id':p['paper_id'],'relevant':True,'reason':'fixture','question_ids':['q1']} for p in payload['papers']]
                elif task.startswith('Extract a literature'):
                    from review_workflow import CARD_FIELDS
                    result={f:{'status':'not_found_in_processed_text','text':'','evidence_ids':[]} for f in CARD_FIELDS}
                    result['findings']={'status':'found','text':'A fixture claim','evidence_ids':[payload['evidence'][0]['evidence_id']]}
                elif task.startswith('Propose 5'):
                    e=payload['evidence'][0]
                    result={'directions':[{'direction_id':'d1','title':'Fixture methods','description':'Compare methods in the fixture','question':'retrieval methods','search_query':'retrieval methods','paper_ids':[e['paper_id']],'evidence_ids':[e['evidence_id']]}]}
                elif task.startswith('Create an academic'):
                    result={'nodes':[{**n,'purpose':'Fixture scope with sources','argument_points':[],'counterevidence_ids':[],
                        'conditions':[],'gaps':[],'user_writing_tasks':[]} for n in payload['skeleton']['nodes']]}
                    for n in result['nodes']:
                        n['question_ids']=['d1']
                    result['nodes'][3]['argument_points']=[{'point_id':'c1','text':'A fixture claim','kind':'author_finding','evidence_ids':[payload['evidence_ids'][0]['evidence_id']],'required_level':'abstract'}]
                else:
                    result={'status':'supported','reason':'fixture auxiliary judgment','contradiction':False}
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))],usage=None)
            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),close=lambda:None)
        with tempfile.TemporaryDirectory() as directory,patch.object(nodes,'create_client',side_effect=factory),patch.object(w,'search',return_value=([paper],[{'status':'success','source':'fixture'}])),patch.object(w,'_get_embedder',return_value=w.DemoEmbedder()):
            app=build_graph()
            config={'configurable':{'thread_id':'byok-fixture'},'recursion_limit':100}
            access=user_access('deepseek','fixture-model','fixture-session-only-key')
            with use_model_access(access):
                app.invoke({'topic':'retrieval','settings':{'cache_dir':directory,'fulltext':False,'min_papers':1,'max_search_rounds':0}},config)
            self.assertTrue(app.get_state(config).interrupts)
            decisions={p['paper_id']:{'decision':'keep','reason':''} for p in app.get_state(config).values['paper_decisions']}
            with use_model_access(access):
                app.invoke(Command(resume={'action':'confirm','decisions':decisions}),config)
                self.assertEqual(app.get_state(config).interrupts[0].value['kind'],'directions')
                app.invoke(Command(resume={'action':'generate','selected_ids':['d1']}),config)
                self.assertEqual(app.get_state(config).interrupts[0].value['kind'],'outline')
                app.invoke(Command(resume={'action':'accept'}),config)
            state=app.get_state(config).values
            self.assertTrue(requests)
            self.assertNotIn('fixture-session-only-key',json.dumps(state))
            from projects import exports
            self.assertNotIn('fixture-session-only-key',json.dumps(exports(state)))
            self.assertEqual(state['telemetry']['model_access']['model'],'fixture-model')
            self.assertEqual(state['claim_checks'][0]['model'],'fixture-model')
            self.assertNotIn('fixture-session-only-key',json.dumps(list(app.get_state_history(config)),default=str))

    def test_web_requires_key_despite_server_env_and_clears_session(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ,{'MOCK_MODE':'0','DEEPSEEK_API_KEY':'fixture-operator-key'}),patch.object(nodes,'create_client') as factory:
            app=AppTest.from_file('streamlit_app.py',default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key='start_research').disabled)
            app.text_input(key='byok_api_key').set_value('fixture-web-user-key').run()
            self.assertFalse(app.button(key='check_connection').disabled)
            self.assertTrue(app.button(key='start_research').disabled)
            app.selectbox(key='byok_provider').select('openai').run()
            self.assertEqual(app.session_state['byok_api_key'],'')
            self.assertTrue(app.button(key='start_research').disabled)
            app.text_input(key='byok_api_key').set_value('fixture-second-key').run()
            app.button(key='byok_clear').click().run()
            self.assertEqual(app.session_state['byok_api_key'],'')
            factory.assert_not_called()


if __name__=='__main__':
    unittest.main()
