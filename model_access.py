"""Ephemeral, context-local credentials. Never put these objects in graph state."""
import contextvars
import os
from contextlib import contextmanager
from dataclasses import dataclass, field

from model_registry import provider_config, IMPLEMENTED_PROVIDERS
PROVIDERS = {name:provider_config(name) for name in IMPLEMENTED_PROVIDERS}



class CredentialsRequired(ValueError):
    """Contains no submitted credential text."""


@dataclass(frozen=True)
class ModelAccess:
    provider: str
    model: str
    api_key: str = field(default="", repr=False)
    demo: bool = False
    semantic_scholar_key: str = field(default="", repr=False)
    display_name: str = ""

    @property
    def base_url(self):
        return provider_config(self.provider)["base_url"]

    def __post_init__(self):
        if self.provider not in PROVIDERS:
            raise CredentialsRequired("Choose a supported provider")
        if not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 200 or any(c.isspace() for c in self.model):
            raise CredentialsRequired("Enter a valid model ID")
        if not self.demo and (not isinstance(self.api_key, str) or not self.api_key.strip() or self.api_key == "your_key_here" or any(c.isspace() for c in self.api_key)):
            raise CredentialsRequired("Your own API key is required")


_CURRENT = contextvars.ContextVar("user_model_access", default=None)


def current_access():
    return _CURRENT.get()


@contextmanager
def use_model_access(access):
    token = _CURRENT.set(access)
    try:
        yield access
    finally:
        _CURRENT.reset(token)


def user_access(provider, model, api_key, *, demo=False, display_name=""):
    """No environment/secrets lookup, even if the server has valid credentials."""
    return ModelAccess(provider, model.strip(), api_key.strip(), demo, display_name=display_name or model.strip())


def local_environment_access():
    """Explicit opt-in for a local CLI or local evaluation operator only. Not used by web."""
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    if provider not in PROVIDERS:
        raise CredentialsRequired("Choose a supported provider")
    cfg = PROVIDERS[provider]
    key = os.getenv(cfg["key_env"], "").strip()
    demo = os.getenv("MOCK_MODE", "").lower() in ("1", "true") or not key or key == "your_key_here"
    return ModelAccess(provider, os.getenv(cfg["model_env"], cfg["default_model"]), key, demo,
                       os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip())


def model_identity():
    access = current_access()
    if access:
        return {"provider": access.provider, "model": access.model, "display_name":access.display_name, "base_url":access.base_url, "mode": "demo" if access.demo else "user_key"}
    return {"provider": "none", "model": "none", "mode": "unconfigured"}


def retired_model(provider, model):
    return provider == "deepseek" and model in ("deepseek-chat", "deepseek-reasoner")


@contextmanager
def local_model_session():
    """Explicit local-operator entry; real web requests must never use this helper."""
    from runtime import ACTIVE, Runtime
    access = current_access() or local_environment_access()
    runtime_token = None
    if ACTIVE.get() is None:
        runtime_token = ACTIVE.set(Runtime({}))
    try:
        with use_model_access(access):
            yield access
    finally:
        if runtime_token is not None:
            ACTIVE.reset(runtime_token)
