"""Provider protocols and model-specific parameter policies, not a shared kwargs bag."""
from dataclasses import dataclass
from model_registry import capabilities, provider_config


@dataclass
class Generation:
    text: str
    http_status: int | None
    usage: dict
    finish_reason: str | None
    parameters: dict


def build_request(access, messages, *, output_limit, task, schema=None):
    if type(output_limit) is not int or not 1 <= output_limit <= 32768:
        raise ValueError('Invalid output token limit')
    caps = capabilities(access.provider, access.model)
    options = {'model':access.model, caps['output_limit']:output_limit}
    if access.provider == 'anthropic':
        system = '\n'.join(m['content'] for m in messages if m['role']=='system')
        options['messages'] = [m for m in messages if m['role']!='system']
        if system:
            options['system'] = system
        if caps['thinking']=='between_tools':
            options['thinking']={'type':'between_tools'}
        if schema and caps['structured']=='anthropic_schema':
            options['output_config']={'format':{'type':'json_schema','schema':schema}}
        # Do not send sampling parameters to Claude models that reject them.
    else:
        options['messages']=messages
        if caps['temperature']:
            options['temperature']=0.3 if task in ('plan','screen','support','revise','filter','translate','api_validation') else .7
        if access.provider=='deepseek' and caps['thinking']=='disabled':
            options['extra_body']={'thinking':{'type':'disabled'}}
        if access.provider=='openai' and caps['thinking']=='minimal':
            options['reasoning_effort']='minimal'
        if schema and caps['structured']=='json_schema':
            options['response_format']={'type':'json_schema','json_schema':{'name':'research_'+task,'strict':True,'schema':schema}}
        elif schema and caps['structured']=='json_object':
            options['response_format']={'type':'json_object'}
        # Unknown custom models use conservative provider defaults: no sampling,
        # thinking or native schema kwargs inferred just from their name.
    return options


def invoke(client, access, messages, *, output_limit, task, schema=None, timeout=20):
    options=build_request(access,messages,output_limit=output_limit,task=task,schema=schema)
    options['timeout']=timeout
    resource=client.messages if access.provider=='anthropic' else client.chat.completions
    raw_api=getattr(resource,'with_raw_response',None)
    if raw_api is not None:
        raw=raw_api.create(**options)
        status=raw.status_code
        response=raw.parse()
    else:
        # Supports injected test transports without inventing HTTP success codes.
        response=resource.create(**options)
        status=getattr(response,'http_status',None)
    usage_obj=getattr(response,'usage',None)
    usage={}
    if access.provider=='anthropic':
        text='\n'.join(b.text for b in response.content if b.type=='text')
        finish=getattr(response,'stop_reason',None)
        if usage_obj:
            usage={'input_tokens':usage_obj.input_tokens,'output_tokens':usage_obj.output_tokens}
    else:
        text=response.choices[0].message.content or ''
        finish=getattr(response.choices[0],'finish_reason',None)
        if usage_obj:
            usage={'input_tokens':usage_obj.prompt_tokens,'output_tokens':usage_obj.completion_tokens,'total_tokens':usage_obj.total_tokens}
    parameters={k:v for k,v in options.items() if k not in ('messages','system','model','response_format','output_config')}
    if schema:
        parameters['structured_output']=capabilities(access.provider,access.model)['structured']
    return Generation(text,status,usage,finish,parameters)
