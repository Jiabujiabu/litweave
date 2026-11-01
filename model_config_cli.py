"""Numbered provider/model/key/validation setup shared with web backend functions."""
from getpass import getpass
import json
from model_access import PROVIDERS, user_access
from model_registry import model_options, CUSTOM_MODEL, provider_config
from model_errors import ModelCallError
from connection_check import refresh_models, verify_generation


def choose_numbered(options, prompt, *, input_fn=input, print_fn=print):
    values=list(options)
    for i,key in enumerate(values,1):
        print_fn(f'[{i}] {options[key]}')
    while True:
        raw=input_fn(prompt).strip()
        if raw.isdigit() and 1<=int(raw)<=len(values):
            return values[int(raw)-1]
        print_fn('请选择有效编号 / Select a valid number.')


def configure_model(lang='en', *, input_fn=None, key_fn=None, print_fn=print):
    input_fn=input_fn or input
    key_fn=key_fn or getpass
    remote={}
    while True:
        provider=choose_numbered({**{p:c['label'] for p,c in PROVIDERS.items()},'demo':'Offline demo / 离线演示','exit':'Exit / 退出'},
                                 '厂商编号 / Provider: ',input_fn=input_fn,print_fn=print_fn)
        if provider=='exit':
            return None
        if provider=='demo':
            return user_access('deepseek',provider_config('deepseek')['default_model'],'',demo=True,display_name='Offline demo')
        def choose_model(selected=None):
            options=model_options(provider,remote.get(provider),selected)
            display={k:f'{label}'+(f' ({k})' if k!=CUSTOM_MODEL else '') for k,label in options.items()}
            chosen=choose_numbered(display,'模型编号 / Model: ',input_fn=input_fn,print_fn=print_fn)
            if chosen==CUSTOM_MODEL:
                model=input_fn('自定义 API ID / Custom model ID: ').strip()
                return model,'Custom: '+model
            return chosen,options[chosen]
        model,name=choose_model()
        key=key_fn('API Key（输入不回显）: ').strip()
        validation=None
        while True:
            try:
                access=user_access(provider,model,key,display_name=name)
            except ValueError as error:
                print_fn('配置无效，请重新选择并输入 / Invalid configuration.')
                break
            action=choose_numbered({'test':'测试连接（一次真实生成，可能产生少量 API 费用，最多64输出tokens）',
                                     'refresh':'刷新模型列表（不验证生成）','model':'更换模型','provider':'更换厂商/Key',
                                     'start':'开始研究','exit':'退出'},'操作编号 / Action: ',input_fn=input_fn,print_fn=print_fn)
            if action=='exit':
                return None
            if action=='provider':
                break
            if action=='model':
                model,name=choose_model(model)
                validation=None
            elif action=='refresh':
                try:
                    listing=refresh_models(access)
                    remote[provider]=listing.get('model_records',[])
                    print_fn('模型列表已刷新；当前选择未更改 / List refreshed; selection unchanged.')
                except ModelCallError as error:
                    print_fn(error.message(lang))
                    print_fn('列表失败不会阻止已配置模型测试 / You can still test the configured model.')
            elif action=='test':
                confirm=input_fn('发送一次真实请求，可能产生少量费用。确认？[y/N]: ').strip().lower()
                if confirm!='y':
                    continue
                validation=verify_generation(access,consent=True,output_limit=64)
                if validation.get('generation_verified'):
                    print_fn('真实生成验证通过 / Real generation passed.')
                else:
                    diagnostic=validation.get('diagnostic') or {}
                    print_fn(ModelCallError(validation.get('category','unknown'),provider=provider,status=diagnostic.get('http_status')).message(lang))
                if validation.get('diagnostic'):
                    print_fn(json.dumps(validation['diagnostic'],ensure_ascii=False))
            elif action=='start':
                if validation and validation.get('generation_verified'):
                    return access
                print_fn('请先完成真实生成验证 / Complete the generation test first.')
