"""Provider policies and UI verification workflow; never real API calls."""
import os
os.environ['MOCK_MODE']='1'
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
import nodes
from model_access import user_access
from model_registry import catalog, model_options, capabilities, CUSTOM_MODEL, CATALOG_PATH
from provider_adapters import build_request, invoke
from connection_check import verify_generation, refresh_models
from model_errors import ModelCallError
from model_schemas import SCHEMAS
from test_byok import fake_client
from test_model_errors import status_error

MESSAGES=[{'role':'system','content':'Return JSON.'},{'role':'user','content':'fixture'}]


class ModelConfiguration(unittest.TestCase):
    def test_presets_sources_dates_names_and_only_implemented_providers(self):
        data=catalog()
        self.assertEqual(set(data['providers']),{'deepseek','openai','anthropic'})
        for p,cfg in data['providers'].items():
            self.assertRegex(cfg['checked_on'],r'^\d{4}-\d{2}-\d{2}$')
            for m in cfg['models']:
                self.assertTrue(m['official_sources'])
                self.assertTrue(m['display_name'])
                self.assertTrue(m['api_id'])
            self.assertIn(CUSTOM_MODEL,model_options(p))

    def test_parameter_policies_are_model_and_provider_specific(self):
        ds=build_request(user_access('deepseek','deepseek-flash','fixture'),MESSAGES,output_limit=64,task='plan',schema=SCHEMAS['plan'])
        self.assertEqual(ds['max_tokens'],64)
        self.assertEqual(ds['extra_body']['thinking']['type'],'disabled')
        self.assertEqual(ds['response_format']['type'],'json_object')
        self.assertNotIn('max_completion_tokens',ds)
        standard=build_request(user_access('openai','gpt-4o-mini','fixture'),MESSAGES,output_limit=64,task='plan',schema=SCHEMAS['plan'])
        self.assertEqual(standard['max_completion_tokens'],64)
        self.assertIn('temperature',standard)
        self.assertNotIn('max_tokens',standard)
        self.assertEqual(standard['response_format']['type'],'json_schema')
        reasoning=build_request(user_access('openai','gpt-5-mini','fixture'),MESSAGES,output_limit=64,task='plan')
        self.assertNotIn('temperature',reasoning)
        self.assertEqual(reasoning['reasoning_effort'],'minimal')
        claude=build_request(user_access('anthropic','claude-sonnet-5-5','fixture'),MESSAGES,output_limit=64,task='plan',schema=SCHEMAS['plan'])
        self.assertEqual(claude['system'],'Return JSON.')
        self.assertEqual(claude['messages'],MESSAGES[1:])
        self.assertNotIn('temperature',claude)
        self.assertEqual(claude['thinking'],{'type':'between_tools'})
        self.assertIn('output_config',claude)
        self.assertNotIn('response_format',claude)

    def test_unknown_custom_model_uses_conservative_policy(self):
        for p in ('openai','deepseek','anthropic'):
            kwargs=build_request(user_access(p,'custom-id','fixture'),MESSAGES,output_limit=64,task='plan',schema=SCHEMAS['plan'])
            self.assertNotIn('temperature',kwargs)
            self.assertNotIn('thinking',kwargs)
            self.assertNotIn('extra_body',kwargs)
            self.assertNotIn('response_format',kwargs)
            self.assertNotIn('output_config',kwargs)

    def test_actual_sdk_serialization_and_response_for_all_protocols(self):
        requests=[]
        def handler(request):
            requests.append((request.url.host,json.loads(request.content)))
            if request.url.host=='api.anthropic.com':
                return httpx.Response(200,json={'id':'msg_fixture','type':'message','role':'assistant','model':'claude-sonnet-5-5',
                    'content':[{'type':'text','text':'OK'}],'stop_reason':'end_turn','stop_sequence':None,'usage':{'input_tokens':5,'output_tokens':1}})
            return httpx.Response(200,json={'id':'fixture','object':'chat.completion','created':0,'model':'fixture',
                'choices':[{'index':0,'message':{'role':'assistant','content':'OK'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':5,'completion_tokens':1,'total_tokens':6}})
        for p,m in [('deepseek','deepseek-flash'),('openai','gpt-5-mini'),('anthropic','claude-sonnet-5-5')]:
            access=user_access(p,m,'fixture-key')
            client=nodes.create_client(access,20,httpx.Client(transport=httpx.MockTransport(handler)))
            try:
                result=invoke(client,access,MESSAGES,output_limit=64,task='plan',schema=SCHEMAS['plan'])
                self.assertEqual(result.text,'OK')
                self.assertEqual(result.http_status,200)
            finally:
                client.close()
        self.assertNotIn('temperature',requests[1][1])
        self.assertNotIn('temperature',requests[2][1])
        self.assertEqual(requests[2][1]['thinking']['type'],'between_tools')

    def test_generation_requires_user_action_and_demo_never_passes(self):
        access=user_access('deepseek','deepseek-flash','fixture')
        with patch.object(nodes,'create_client') as create:
            with self.assertRaises(ModelCallError):
                verify_generation(access)
            demo=verify_generation(user_access('deepseek','deepseek-flash','',demo=True),consent=True)
            self.assertFalse(demo['generation_verified'])
            create.assert_not_called()

    def test_generation_one_request_capped_and_failures_never_pass(self):
        for status,code in [(404,'model_not_found'),(403,'forbidden'),(400,'unsupported_parameter'),(429,'rate_limit')]:
            with patch.object(nodes,'create_client',return_value=fake_client(error=status_error(status,code,'temperature'))) as create:
                result=verify_generation(user_access('deepseek','deepseek-flash','fixture-secret-key'),consent=True,output_limit=32)
                self.assertFalse(result['generation_verified'])
                self.assertEqual(result['diagnostic']['http_status'],status)
                self.assertEqual(result['diagnostic']['base_url'],'https://api.deepseek.com')
                self.assertNotIn('fixture-secret-key',json.dumps(result))
                self.assertEqual(create.call_count,1)

    def test_remote_options_preserve_selection_and_catalog(self):
        before=CATALOG_PATH.read_bytes()
        options=model_options('deepseek',[{'api_id':'remote-id','display_name':'Remote model'}],selected_id='previous-id')
        self.assertEqual(options['remote-id'],'Remote model')
        self.assertIn('previous-id',options)
        self.assertIn(CUSTOM_MODEL,options)
        self.assertEqual(before,CATALOG_PATH.read_bytes())

    def test_diagnostic_records_selected_provider_url_model_and_redacted_detail(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'RESEARCH_API_DIAGNOSTICS':str(Path(directory)/'events.jsonl')}):
            with patch.object(nodes,'create_client',return_value=fake_client(error=status_error(400,'unsupported_parameter','temperature'))):
                access=user_access('deepseek','custom-id','fixture-secret-key',display_name='Custom test model')
                result=verify_generation(access,consent=True)
            text=(Path(directory)/'events.jsonl').read_text(encoding='utf-8')
            self.assertNotIn('fixture-secret-key',text)
            event=json.loads(text)
            self.assertEqual(event['model_display_name'],'Custom test model')
            self.assertEqual(event['model_id'],'custom-id')
            self.assertEqual(event['provider'],'deepseek')
            self.assertEqual(event['http_status'],400)
            self.assertTrue(event['error_message'])

    def test_web_list_failure_does_not_block_generation_or_change_model(self):
        import connection_check
        from streamlit.testing.v1 import AppTest
        passed={'status':'passed','generation_verified':True,'response_preview':'OK','diagnostic':{'provider':'deepseek','model_id':'deepseek-flash','http_status':200}}
        with patch.dict(os.environ,{'MOCK_MODE':'0'}),patch.object(connection_check,'refresh_models',side_effect=ModelCallError('permission',provider='deepseek',status=403)),patch.object(connection_check,'verify_generation',return_value=passed) as verify:
            app=AppTest.from_file('streamlit_app.py',default_timeout=30).run()
            self.assertNotIn('google',app.selectbox(key='byok_provider').options)
            app.text_input(key='byok_api_key').set_value('fixture-key').run()
            current=app.session_state['selected_model_id']
            app.button(key='refresh_models').click().run()
            self.assertEqual(app.session_state['selected_model_id'],current)
            self.assertFalse(app.button(key='check_connection').disabled)
            self.assertTrue(app.button(key='start_research').disabled)
            app.button(key='check_connection').click().run()
            self.assertTrue(app.session_state['connection_result']['generation_verified'])
            self.assertFalse(app.button(key='start_research').disabled)
            self.assertEqual(verify.call_args.args[0].api_key,'fixture-key')
            app.selectbox(key='byok_model_choice').select('deepseek-v4-pro').run()
            self.assertIsNone(app.session_state['connection_result'])
            self.assertTrue(app.button(key='start_research').disabled)
            self.assertFalse(app.exception)

    def test_web_refresh_success_is_not_generation_success(self):
        import connection_check
        from streamlit.testing.v1 import AppTest
        listing={'status':'ok','model_records':[{'api_id':'remote-new','display_name':'New remote model'}],'generation_verified':False}
        with patch.dict(os.environ,{'MOCK_MODE':'0'}),patch.object(connection_check,'refresh_models',return_value=listing),patch.object(connection_check,'verify_generation') as verify:
            app=AppTest.from_file('streamlit_app.py',default_timeout=30).run()
            app.text_input(key='byok_api_key').set_value('fixture-key').run()
            app.button(key='refresh_models').click().run()
            self.assertEqual(app.session_state['selected_model_id'],'deepseek-flash')
            self.assertTrue(app.button(key='start_research').disabled)
            verify.assert_not_called()
            self.assertIn('New remote model',app.selectbox(key='byok_model_choice').options)

    def test_cli_numbered_flow_uses_selected_key_after_explicit_test(self):
        import model_config_cli as cli
        answers=iter(['3','1','1','y','5'])
        output=[]
        with patch.object(cli,'verify_generation',return_value={'status':'passed','generation_verified':True,'diagnostic':None}) as verify:
            access=cli.configure_model(input_fn=lambda _:next(answers),key_fn=lambda _:'fixture-cli-key',print_fn=output.append)
        self.assertEqual(access.provider,'deepseek')
        self.assertEqual(access.model,'deepseek-flash')
        self.assertEqual(access.api_key,'fixture-cli-key')
        self.assertNotIn('fixture-cli-key',' '.join(output))
        self.assertTrue(verify.call_args.kwargs['consent'])

    def test_cli_declined_fee_does_not_call_generation(self):
        import model_config_cli as cli
        answers=iter(['3','1','1','n','6'])
        with patch.object(cli,'verify_generation') as verify:
            access=cli.configure_model(input_fn=lambda _:next(answers),key_fn=lambda _:'fixture-key',print_fn=lambda _:None)
        self.assertIsNone(access)
        verify.assert_not_called()

    def test_cli_without_environment_key_still_opens_configuration(self):
        import main
        with patch.dict(os.environ,{'MOCK_MODE':'0'}),patch.object(main,'configure_model',return_value=None) as configure,patch('builtins.input',return_value='1'),patch('builtins.print'):
            main.main()
        configure.assert_called_once_with('en')

    def test_web_migration_preserves_existing_provider_and_custom_id(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ,{'MOCK_MODE':'0'}):
            app=AppTest.from_file('streamlit_app.py',default_timeout=30)
            app.session_state['byok_provider']='anthropic'
            app.session_state['byok_model']='previous-custom-id'
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['byok_provider'],'anthropic')
            self.assertEqual(app.session_state['selected_model_id'],'previous-custom-id')
            self.assertEqual(app.session_state['byok_model_choice'],CUSTOM_MODEL)


if __name__=='__main__':
    unittest.main()
