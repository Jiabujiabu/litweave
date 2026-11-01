"""Per-run budgets and redacted telemetry shared by both entry points."""
import contextvars
import copy
import time
import uuid
from functools import wraps
from settings import Settings

ACTIVE = contextvars.ContextVar("research_runtime", default=None)


class BudgetExceeded(RuntimeError):
    pass


class Runtime:
    def __init__(self, state):
        self.settings = Settings.load(state.get("settings"))
        self.data = copy.deepcopy(state.get("telemetry") or {})
        self.data.setdefault("run_id", state.get("run_id") or uuid.uuid4().hex)
        for k in ("requests", "model_calls", "reserved_tokens", "reported_tokens"):
            self.data.setdefault(k, 0)
        self.data.setdefault("stages", [])
        self.data.setdefault("models", [])
        from model_access import model_identity
        self.data["model_access"] = model_identity()
        self.data.setdefault("cost", "unknown")
        self.data.setdefault("token_usage", "unknown")

    def request(self):
        if self.data["requests"] >= self.settings.max_requests:
            raise BudgetExceeded("request budget exhausted")
        self.data["requests"] += 1

    def model(self, messages, model, output_limit=None):
        # One Unicode codepoint per input token is a conservative engineering estimate.
        output_limit=self.settings.max_output_tokens if output_limit is None else output_limit
        if type(output_limit) is not int or not 1<=output_limit<=self.settings.max_output_tokens:
            raise ValueError('Invalid output reservation')
        reservation = sum(len(m["content"]) + 32 for m in messages) + output_limit
        if self.data["model_calls"] >= self.settings.max_model_calls or self.data["reserved_tokens"] + reservation > self.settings.max_total_tokens:
            raise BudgetExceeded("model call/token reservation budget exhausted")
        self.request()
        self.data["model_calls"] += 1
        self.data["reserved_tokens"] += reservation
        if model not in self.data["models"]:
            self.data["models"].append(model)


def stage(fn):
    @wraps(fn)
    def run(state):
        runtime = Runtime(state)
        token = ACTIVE.set(runtime)
        started = time.monotonic()
        try:
            update = fn(state)
            runtime.data["stages"].append({"stage": fn.__name__, "seconds": round(time.monotonic() - started, 4)})
            update["telemetry"] = runtime.data
            update["run_id"] = runtime.data["run_id"]
            update["settings"] = runtime.settings.to_dict()
            return update
        finally:
            ACTIVE.reset(token)
    return run


def config():
    active = ACTIVE.get()
    return active.settings if active else Settings.load()
