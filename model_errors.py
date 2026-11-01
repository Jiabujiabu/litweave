"""Safe, actionable model errors without response bodies, prompts or credentials."""
import re


class ModelCallError(RuntimeError):
    def __init__(self, category="unknown", *, provider=None, model=None, status=None, parameter=None, detail="", code=None):
        self.category = category
        # Only stable categories/numbers/known parameter names are retained. SDK error
        # bodies and messages can echo credentials or submitted text and are not saved.
        self.provider = provider if provider in ("deepseek", "openai", "anthropic") else None
        self.model = model if isinstance(model, str) and re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,150}", model) else None
        self.status = status if type(status) is int and 100 <= status <= 599 else None
        self.parameter = parameter if parameter in ("model", "max_tokens", "max_completion_tokens", "temperature", "messages", "response_format", "thinking", "reasoning_effort") else None
        self.detail = detail
        self.code = code
        self.diagnostic = None
        super().__init__(self.message("en"))

    def message(self, lang="en"):
        zh = lang == "zh"
        messages = {
            "authentication": ("API Key 验证失败。请核对服务商与 Key 是否匹配、Key 是否仍有效。", "API key authentication failed. Check the provider and that your key is valid."),
            "balance": ("模型 API 账户余额不足。请检查所选服务商 API 账户的余额。", "The model API account has insufficient balance. Check your provider's API balance."),
            "quota": ("模型 API 额度不足或已达账户用量上限。请检查账户额度。", "Model API quota or account usage limit reached. Check your account limits."),
            "permission": ("账户没有所选模型或接口的访问权限，或所在地区受限。", "Access to this model/API is denied, or the region is restricted."),
            "model_unavailable": ("模型 ID 不存在、已停用或当前账户不可访问。请检查模型 ID。", "The model ID is unavailable, retired or inaccessible to this account. Check the model ID."),
            "endpoint_not_found": ("接口地址或请求路径不存在，请核对服务商接口配置。", "The API endpoint/path was not found. Check the provider configuration."),
            "consent_required": ("请先确认本次真实测试可能产生少量 API 费用。", "Confirm the possible small API charge before running a real generation test."),
            "mock_not_verified": ("演示模式不执行真实 API 验证，也不计为验证成功。", "Demo mode does not verify a real API and cannot pass validation."),
            "retired_model": ("这个 DeepSeek 旧模型名已停用。请明确改用 deepseek-flash 后重试。", "This legacy DeepSeek model name is retired. Explicitly select deepseek-flash and retry."),
            "rate_limit": ("请求过于频繁或达到并发限制，请稍后重试。", "Rate or concurrency limit reached. Wait and retry."),
            "timeout": ("模型接口请求超时。请检查网络，或提高请求超时设置后重试。", "The model request timed out. Check connectivity or increase the request timeout."),
            "connection": ("无法连接模型服务。请检查网络、代理和证书设置。", "Cannot connect to the model service. Check network, proxy and certificate settings."),
            "invalid_request": ("模型拒绝了请求参数。请核对模型及参数支持情况。", "The model rejected request parameters. Check model and parameter compatibility."),
            "service_unavailable": ("模型服务暂时不可用或繁忙，请稍后重试。", "The model service is temporarily unavailable or busy. Retry later."),
            "sdk_configuration": ("模型客户端与运行环境不兼容。请使用仓库 .venv 启动，或更新 requirements.txt 中的依赖。", "Model client/environment mismatch. Start with this repository's .venv or update its requirements."),
            "empty_response": ("模型没有返回可用正文，可能只返回推理内容或达到输出上限。", "The model returned no usable text; it may have returned only reasoning or reached the output limit."),
            "invalid_json": ("模型返回内容不是有效 JSON，本次研究未能完成结构化处理。", "The model response was not valid JSON; structured processing could not finish."),
            "runtime_configuration": ("研究请求缺少运行预算上下文。请重启应用后重试。", "The research request has no run-budget context. Restart the application and retry."),
            "unknown": ("模型调用失败。错误详情未包含可安全显示的原因。", "The model request failed without a safely identifiable cause."),
        }
        text = messages.get(self.category, messages["unknown"])[0 if zh else 1]
        tags = []
        if self.provider:
            tags.append(self.provider)
        if self.status:
            tags.append("HTTP " + str(self.status))
        if self.parameter:
            tags.append(("参数 " if zh else "parameter ") + self.parameter)
        # Model IDs are shown in their own input field; do not echo arbitrary input.
        return text + (" [" + "; ".join(tags) + "]" if tags else "")


def classify_model_error(error, access):
    if isinstance(error, ModelCallError):
        return error
    status = getattr(error, "status_code", None)
    body = getattr(error, "body", None)
    data = body.get("error", body) if isinstance(body, dict) else {}
    data = data if isinstance(data, dict) else {}
    # Inspect only code/type and a tiny parameter allowlist, never echo raw bodies.
    code = " ".join(str(data.get(k) or "").lower() for k in ("code", "type"))
    name = type(error).__name__
    if status == 401:
        category = "authentication"
    elif status == 402:
        category = "balance"
    elif status == 403:
        category = "permission"
    elif "model_not_found" in code or (status == 404 and re.search(r'\bmodel\b', str(data.get('message') or ''),re.I)):
        category = "model_unavailable"
    elif status == 404:
        category = "endpoint_not_found"
    elif status == 429:
        category = "quota" if any(x in code for x in ("insufficient_quota", "billing_hard_limit", "quota_exceeded")) else "rate_limit"
    elif status in (408, 504) or "Timeout" in name:
        category = "timeout"
    elif isinstance(status, int) and status >= 500:
        category = "service_unavailable"
    elif status in (400, 413, 422):
        category = "invalid_request"
    elif "Connection" in name or isinstance(error, ConnectionError):
        category = "connection"
    elif isinstance(error, (TypeError, ImportError)):
        category = "sdk_configuration"
    else:
        category = "unknown"
    from api_diagnostics import redact
    detail = redact(data.get('message'),(access.api_key,access.semantic_scholar_key))
    if not detail:
        detail = name  # class name only; never raw SDK exception text/headers
    provider_code=redact(data.get('code') or data.get('type'),(access.api_key,access.semantic_scholar_key),100)
    return ModelCallError(category, provider=access.provider, model=access.model, status=status,
                          parameter=data.get("param"),detail=detail,code=provider_code or None)
