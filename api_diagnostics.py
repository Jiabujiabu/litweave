"""Credential-free request events. No prompts or full model responses are logged."""
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def redact(value, secrets=(), limit=500):
    text = str(value or '')
    for secret in secrets:
        if secret:
            for part in (secret, secret[:8] if len(secret) >= 16 else '', secret[-8:] if len(secret) >= 16 else ''):
                if part:
                    text = text.replace(part, '[REDACTED]')
    text = re.sub(r'(?i)bearer\s+[^\s,;"\']+', 'Bearer [REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{4,}', '[REDACTED]', text)
    text = re.sub(r'(?i)(api[_ -]?key|authorization|access[_ -]?token)\s*[:=]\s*[^\s,;]+', r'\1=[REDACTED]', text)
    # Do not store a response that embeds request messages or headers.
    if re.search(r'(?i)["\'](?:messages|headers|prompt)["\']\s*:', text):
        text = '[request content omitted]'
    return ' '.join(text.split())[:limit]


def safe_base_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.hostname or '', parts.path, '', ''))


def request_event(access, operation, *, status=None, category=None, detail='', code=None,
                  parameter=None, seconds=None, usage=None, request_parameters=None):
    secrets = (access.api_key, access.semantic_scholar_key)
    return {'event_id':uuid.uuid4().hex, 'time_utc':datetime.now(timezone.utc).isoformat(),
            'execution_context':os.getenv('RESEARCH_DIAGNOSTICS_CONTEXT','application'),
            'operation':operation, 'provider':access.provider, 'base_url':safe_base_url(access.base_url),
            'model_id':redact(access.model,secrets,150), 'model_display_name':redact(access.display_name,secrets,150),
            'http_status':status, 'category':category, 'error_message':redact(detail,secrets),
            'provider_error_code':redact(code,secrets,100) if code else None,
            'parameter':parameter, 'seconds':round(seconds,3) if seconds is not None else None,
            'usage':usage or None, 'request_parameters':request_parameters or {}}


def record_event(event):
    # Failed diagnostic persistence must not turn successful API generation into failure.
    try:
        path = Path(os.getenv('RESEARCH_API_DIAGNOSTICS', '.research_runs/api_diagnostics/events.jsonl'))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(event,ensure_ascii=False)+'\n')
        return True
    except OSError:
        return False
