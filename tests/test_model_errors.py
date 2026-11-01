"""Model compatibility and actionable errors; synthetic keys/responses only."""
import os
os.environ['MOCK_MODE']='1'
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import openai
import nodes
from model_access import PROVIDERS, user_access
from model_errors import ModelCallError, classify_model_error
from connection_check import check_connection
from test_byok import call_context, fake_client


def status_error(status, code='invalid_request_error', parameter=None):
    request=httpx.Request('POST','https://api.deepseek.com/chat/completions')
    response=httpx.Response(status,request=request)
    body={'error':{'message':'Never echo fixture-secret-key or submitted private text','code':code,'param':parameter}}
    return openai.APIStatusError('SDK error includes fixture-secret-key',response=response,body=body)


class ModelErrors(unittest.TestCase):
    def test_legacy_custom_id_is_classified_by_actual_response_not_assumed(self):
        self.assertEqual(PROVIDERS['deepseek']['default_model'],'deepseek-flash')
        with call_context('fixture-key',model='deepseek-chat'),patch.object(nodes,'create_client',return_value=fake_client(error=status_error(401))) as create:
            with self.assertRaises(ModelCallError) as error:
                nodes.call_llm([{'role':'user','content':'fixture'}],task='plan',language='en')
            self.assertEqual(error.exception.category,'authentication')
            self.assertEqual(create.call_count,1)

    def test_deepseek_requests_non_thinking_explicitly(self):
        options=[]
        client=fake_client()
        original=client.chat.completions.create
        def create(**kwargs):
            options.append(kwargs)
            return original(**kwargs)
        client.chat.completions.create=create
        with call_context('fixture-key',model='deepseek-flash'),patch.object(nodes,'create_client',return_value=client):
            nodes.call_llm([{'role':'user','content':'fixture'}],task='plan',language='en')
        self.assertEqual(options[0]['model'],'deepseek-flash')
        self.assertEqual(options[0]['extra_body'],{'thinking':{'type':'disabled'}})

    def test_http_errors_actionable_without_key_or_raw_body(self):
        access=user_access('deepseek','deepseek-flash','fixture-secret-key')
        cases=[(401,'invalid_api_key','authentication'),(402,'insufficient_balance','balance'),
               (403,'forbidden','permission'),(404,'model_not_found','model_unavailable'),
               (422,'invalid_request_error','invalid_request'),(429,'rate_limit','rate_limit'),
               (429,'insufficient_quota','quota'),(500,'server_error','service_unavailable')]
        for status,code,expected in cases:
            error=classify_model_error(status_error(status,code,'fixture-secret-key'),access)
            self.assertEqual(error.category,expected)
            self.assertIn('HTTP '+str(status),error.message('zh'))
            self.assertNotIn('fixture-secret-key',str(error))
            self.assertNotIn('submitted private text',error.message('zh'))
            self.assertIsNone(error.parameter)

    def test_transport_and_sdk_errors_distinguished(self):
        access=user_access('deepseek','deepseek-flash','fixture-key')
        request=httpx.Request('POST','https://api.deepseek.com/chat/completions')
        for original,expected in [(openai.APITimeoutError(request),'timeout'),
                                  (openai.APIConnectionError(request=request),'connection'),
                                  (TypeError('unexpected keyword admin_api_key'),'sdk_configuration')]:
            self.assertEqual(classify_model_error(original,access).category,expected)

    def test_generation_error_preserves_safe_status(self):
        with call_context('fixture-secret-key',model='deepseek-flash'),patch.object(nodes,'create_client',return_value=fake_client(error=status_error(402))):
            with self.assertRaises(ModelCallError) as caught:
                nodes.call_llm([{'role':'user','content':'fixture'}],task='plan',language='zh')
            self.assertEqual(caught.exception.category,'balance')
            self.assertIn('余额',caught.exception.message('zh'))

    def test_connection_check_only_reads_metadata_and_balance_flag(self):
        requests=[]
        def handler(request):
            requests.append((request.method,request.url.path))
            self.assertEqual(request.headers['authorization'],'Bearer fixture-key')
            if request.url.path=='/models':
                return httpx.Response(200,json={'object':'list','data':[{'id':'deepseek-flash','object':'model','owned_by':'deepseek'}]})
            if request.url.path=='/user/balance':
                return httpx.Response(200,json={'is_available':False,'balance_infos':[{'total_balance':'private-account-amount'}]})
            self.fail('Metadata check must not call generation')
        original=nodes.create_client
        with patch.object(nodes,'create_client',side_effect=lambda access,timeout: original(access,timeout,httpx.Client(transport=httpx.MockTransport(handler)))):
            result=check_connection(user_access('deepseek','deepseek-flash','fixture-key'))
        self.assertEqual(requests,[('GET','/models'),('GET','/user/balance')])
        self.assertFalse(result['balance_available'])
        self.assertNotIn('fixture-key',json.dumps(result))
        self.assertNotIn('private-account-amount',json.dumps(result))

    def test_web_custom_id_preserved_and_no_operator_copy(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ,{'MOCK_MODE':'0'}),patch.object(nodes,'create_client') as create:
            app=AppTest.from_file('streamlit_app.py',default_timeout=30).run()
            text=' '.join(str(x.value) for group in (app.info,app.caption) for x in group)
            self.assertNotIn("operator's key",text)
            app.selectbox(key='byok_model_choice').select('__custom__').run()
            app.text_input(key='byok_custom_id').set_value('deepseek-chat').run()
            app.text_input(key='byok_api_key').set_value('fixture-key').run()
            self.assertEqual(app.session_state['selected_model_id'],'deepseek-chat')
            self.assertFalse(app.button(key='check_connection').disabled)
            self.assertTrue(app.button(key='start_research').disabled)
            create.assert_not_called()

    def test_real_mode_web_error_shows_http_reason_instead_of_class_name(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ,{'MOCK_MODE':'0'}),patch.object(nodes,'create_client',return_value=fake_client(error=status_error(401))):
            app=AppTest.from_file('streamlit_app.py',default_timeout=30).run()
            app.text_input(key='byok_api_key').set_value('fixture-secret-key').run()
            app.button(key='check_connection').click().run()
            self.assertFalse(app.exception)
            errors=' '.join(str(x.value) for x in app.error)
            self.assertIn('HTTP 401',errors)
            self.assertNotIn('ModelCallError',errors)
            self.assertNotIn('fixture-secret-key',errors)


if __name__=='__main__':
    unittest.main()
