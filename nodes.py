"""Provider transport. Real calls require explicit ephemeral user credentials."""
import os
import json
from dotenv import load_dotenv
from model_access import (PROVIDERS, current_access, model_identity, CredentialsRequired)
from model_errors import ModelCallError, classify_model_error

load_dotenv()

# Compatibility metadata for local CLI/evaluation. No API key/client is held globally.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
_provider_cfg = PROVIDERS.get(LLM_PROVIDER, PROVIDERS["deepseek"])
_MODEL = os.getenv(_provider_cfg["model_env"], _provider_cfg["default_model"])
MOCK_MODE = os.getenv("MOCK_MODE", "").lower() in ("1", "true") or not os.getenv(_provider_cfg["key_env"]) or os.getenv(_provider_cfg["key_env"]) == "your_key_here"


def in_demo_mode():
    access = current_access()
    return access.demo if access is not None else MOCK_MODE


def _mock_llm(task, language, **ctx):
    if task == "decompose":
        return json.dumps({"domain":"cs", "directions":[ctx.get("topic", "offline demo")]}, ensure_ascii=False)
    return "[MOCK / DEMO] No real model judgment or scientific conclusion was generated."


def _safe_headers(prefix, omit, auth_name, auth_value):
    # SDKs also read *_CUSTOM_HEADERS from the process environment. Suppress those
    # per client (never mutate global os.environ), then explicitly set user auth last.
    names = [line.split(":", 1)[0].strip() for line in os.getenv(prefix + "_CUSTOM_HEADERS", "").splitlines() if ":" in line]
    headers = {name: omit for name in names if name}
    headers.update({"OpenAI-Organization": omit, "OpenAI-Project": omit})
    for name, value in ((auth_name, auth_value), ("Content-Type", "application/json"), ("Accept", "application/json")):
        headers.pop(name, None)
        headers[name] = value
    return headers


def create_client(access, timeout, http_client=None):
    from model_registry import provider_config
    cfg = provider_config(access.provider)
    if access.provider == "anthropic":
        import anthropic
        headers = _safe_headers("ANTHROPIC", anthropic.omit, "X-Api-Key", access.api_key)
        headers["Authorization"] = anthropic.omit
        headers["anthropic-version"] = "2023-06-01"
        return anthropic.Anthropic(api_key=access.api_key, base_url=cfg["base_url"],
                                   default_headers=headers, webhook_key="", http_client=http_client,
                                   timeout=timeout, max_retries=0)
    from openai import OpenAI, omit
    # Explicit endpoint/key and no server organization/project default or global client.
    return OpenAI(api_key=access.api_key, base_url=cfg["base_url"], organization="", project="", admin_api_key="", webhook_secret="",
                  default_headers=_safe_headers("OPENAI", omit, "Authorization", "Bearer " + access.api_key), http_client=http_client,
                  timeout=timeout, max_retries=0)


def call_llm(messages, *, task, language, **ctx):
    access = current_access()
    if access is None:
        if MOCK_MODE:
            return _mock_llm(task, language, **ctx)
        raise CredentialsRequired("Explicit user credentials are required; server keys are not a fallback")
    if access.demo:
        return _mock_llm(task, language, **ctx)
    from runtime import ACTIVE, config
    active = ACTIVE.get()
    limits = config()
    if active is None:
        # Real entry points must bind a run budget as well as the user's credentials.
        raise ModelCallError("runtime_configuration", provider=access.provider)
    from provider_adapters import invoke,build_request
    output_limit=min(limits.max_output_tokens,{'card':2048,'support':384}.get(task,limits.max_output_tokens))
    options=build_request(access,messages,output_limit=output_limit,task=task,schema=ctx.get('response_schema'))
    budget_messages=list(messages)
    # Reserve only structures actually sent. JSON-object providers do not receive a schema.
    for name in ('response_format','output_config'):
        if name in options:budget_messages.append({'content':json.dumps(options[name])})
    active.model(budget_messages, access.model,output_limit=output_limit)
    from api_diagnostics import request_event, record_event
    import time
    started=time.monotonic()
    client=None
    try:
        client=create_client(access, limits.timeout)
        result=invoke(client,access,messages,output_limit=output_limit,task=task,
                      schema=ctx.get("response_schema"),timeout=limits.timeout)
        if not result.text.strip():
            raise ModelCallError("empty_response",provider=access.provider,model=access.model,status=result.http_status)
        if result.usage:
            active.data["reported_tokens"] += result.usage.get("total_tokens",result.usage.get("input_tokens",0)+result.usage.get("output_tokens",0))
            active.data["token_usage"]="provider_reported"
        record_event(request_event(access,"research:"+task,status=result.http_status,seconds=time.monotonic()-started,
                                   usage=result.usage,request_parameters=result.parameters))
        return result.text
    except Exception as original:
        error=classify_model_error(original,access)
        event=request_event(access,"research:"+task,status=error.status,category=error.category,detail=error.detail,
                            code=error.code,parameter=error.parameter,seconds=time.monotonic()-started)
        record_event(event)
        error.diagnostic=event
        raise error from None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass



# Both front ends and historical scripts retain their imports.
from workflow import (decompose_directions, search_arxiv, search_crossref,
    search_semantic_scholar, process_papers, summarize_literature, human_approval,
    generate_report, verify_citations, prepare_evidence, prepare_report_evidence,
    prepare_feedback, supplementary_search, _embedding_shortlist, _get_embedder,
    _llm_filter_relevant, TOP_K_PAPERS, MIN_PAPERS)
