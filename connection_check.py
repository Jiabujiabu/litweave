"""Separate user-triggered model discovery and fee-consented generation validation."""
import re
from model_errors import ModelCallError, classify_model_error
from api_diagnostics import request_event, record_event
import time


def refresh_models(access, timeout=20):
    if access.demo:
        return {"status": "demo", "models": [], "balance_available": None}
    from nodes import create_client
    started=time.monotonic()
    client = None
    try:
        client = create_client(access, timeout)
        raw_api=getattr(client.models,'with_raw_response',None)
        if raw_api is not None:
            raw=raw_api.list()
            status=raw.status_code
            result=raw.parse()
        else:
            result=client.models.list()
            status=None
        ids = sorted({m.id for m in result.data if isinstance(m.id, str) and re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,150}", m.id)})
        visible = access.model in ids
        balance_available = None
        if access.provider == "deepseek":
            # Optional account-status lookup; do not retain amounts or personal data.
            # Restricted keys may lack this permission while still allowing generation.
            try:
                balance = client.get("/user/balance", cast_to=dict)
                if isinstance(balance, dict) and type(balance.get("is_available")) is bool:
                    balance_available = balance["is_available"]
            except Exception:
                pass
        models=[{"api_id":m.id,"display_name":getattr(m,"display_name",None) or getattr(m,"name",None) or m.id} for m in result.data if m.id in ids]
        event=request_event(access,"model_list_refresh",status=status,seconds=time.monotonic()-started)
        record_event(event)
        return {"status": "ok" if visible else "model_not_listed", "models": ids[:200],
                "model_records":models[:200],"balance_available":balance_available,"generation_verified":False,"diagnostic":event}
    except Exception as original:
        error=classify_model_error(original,access)
        event=request_event(access,"model_list_refresh",status=error.status,category=error.category,detail=error.detail,code=error.code,parameter=error.parameter,seconds=time.monotonic()-started)
        record_event(event)
        error.diagnostic=event
        raise error from None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


# Compatibility name for historical tests/callers. This never verifies generation.
check_connection = refresh_models


def verify_generation(access, *, consent=False, output_limit=64, timeout=60):
    """Exactly one bounded real generation, only after an explicit user action."""
    if not consent:
        raise ModelCallError("consent_required",provider=access.provider,model=access.model)
    if access.demo:
        return {"status":"not_verified","category":"mock_not_verified","generation_verified":False,"diagnostic":None}
    if type(output_limit) is not int or not 1 <= output_limit <= 256:
        raise ValueError("Validation output limit must be 1..256 tokens")
    # Re-run validation for a potentially hand-constructed configuration.
    access.__post_init__()
    from nodes import create_client
    from provider_adapters import invoke
    started=time.monotonic()
    client=None
    try:
        client=create_client(access,timeout)
        result=invoke(client,access,[{"role":"user","content":"Reply with OK only."}],
                      output_limit=output_limit,task="api_validation",timeout=timeout)
        if not result.text.strip():
            raise ModelCallError("empty_response",provider=access.provider,model=access.model,status=result.http_status)
        from api_diagnostics import redact
        event=request_event(access,"api_validation",status=result.http_status,seconds=time.monotonic()-started,
                            usage=result.usage,request_parameters=result.parameters)
        record_event(event)
        return {"status":"passed","generation_verified":True,"response_preview":redact(result.text,(access.api_key,),80),
                "output_limit":output_limit,"diagnostic":event}
    except Exception as original:
        error=classify_model_error(original,access)
        event=request_event(access,"api_validation",status=error.status,category=error.category,detail=error.detail,
                            code=error.code,parameter=error.parameter,seconds=time.monotonic()-started)
        record_event(event)
        error.diagnostic=event
        return {"status":"failed","generation_verified":False,"category":error.category,"diagnostic":event}
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
