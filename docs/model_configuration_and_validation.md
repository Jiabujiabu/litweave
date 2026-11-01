# 模型配置与 API 验证：交付说明

日期：2026-10-31（America/Chicago）。仓库：`./academic-research-agent`。

本轮仅处理模型配置、调用协议、API 验证和诊断。检索提速、标题显示和筛选规则升级没有在本轮展开。

## 真实验证结果

| 服务商 / API ID | 实际状态 |
| --- | --- |
| DeepSeek / deepseek-flash | **真实生成通过：HTTP 200，回复 OK** |
| DeepSeek / deepseek-v4-pro | 本轮未发送请求 |
| OpenAI / gpt-4o-mini、gpt-5-mini | 缺 Key，真实请求未验证 |
| Anthropic / claude-sonnet-5-5、claude-haiku-5-5、claude-opus-5-5 | 缺 Key，真实请求未验证 |
| Google | 未实现 adapter，不展示选项 |

本轮先完成 DeepSeek 的受限真实请求，再完成其余两家协议和离线回归。该请求使用本地已有 Key，提示词仅 `Reply with OK only.`，输出上限 32 token，HTTP 200，正文 `OK`，耗时 **3.379 秒**，服务商报告输入 **9** token、输出 **1** token、合计 **10** token。

费用可能由 API 账户产生；没有用“本地运行”或 token 数较少声称免费，实际账单金额未查询。没有追加其他真实生成请求。这只验证该 Key/模型组合的简单生成链路，不等于完整论文调研、结构化输出、检索质量或其他模型均已验证。

之前失败的 deepseek-chat 请求没有保存原始响应，不能追溯其确切 HTTP 状态或断言是模型名、认证或余额问题。本轮取消按旧模型名直接拦截的逻辑；自定义 ID 会实际请求并按响应分类。

## 网页流程

1. 重启一次 Streamlit 后台，打开页面。
2. 选择厂商，再选择模型预设；显示名称与实际 API ID 分开保存和显示。
3. “自定义模型 ID”始终可选，手动 ID 不会被列表刷新替换。
4. 输入该厂商的 API Key。
5. 可选“刷新模型列表”：只获取元数据；失败不禁用已配置模型的测试，也不算生成验证通过。
6. 阅读费用提示后点击“测试连接”：仅该点击触发一次真实生成，默认最多 64 个输出 token、60 秒超时，SDK 不自动重试。
7. 只有真实生成成功才显示通过，并允许开始真实研究。切换厂商/模型/Key/演示模式后必须重新验证。

模型预设通过不等于当前访问者的 Key 已验证。每位访问者只使用自己的 Key，未配置时不借用服务器账户。Key 不进入研究状态、检查点、导出或诊断日志；会话内存和所选服务商仍是必经处理环节。

启动：

```powershell
cd path/to/academic-research-agent
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

## CLI 流程

`main.py` 现在同样提供厂商编号→模型编号/自定义 ID→不回显的 Key 输入→测试/刷新/更换配置/开始研究菜单。真实测试前会提示费用并要求确认。没有在环境中放 Key 也可以进入配置，交互 CLI 不会把“缺环境 Key”自动当作演示。

```powershell
$env:MOCK_MODE="0"
.\.venv\Scripts\python.exe main.py
```

显式 `MOCK_MODE=1` 仍用于离线演示，不能标为 API 验证成功。批量评测保留明确的本地环境配置入口；网页和交互 CLI 不通过该入口替访问者付费。

## 预设与协议

`config/model_presets.json` 保存预设，`model_registry.py` 加载与校验。每个预设记录显示名称、API ID、协议能力、官方来源和核对日期 **2026-10-31**；用户所选配置不随远端列表刷新改变。未知自定义模型使用保守参数，不根据名称盲目推断全部能力。

| 配置 | 参数处理 |
| --- | --- |
| DeepSeek 已核对预设 | Chat Completions，max_tokens；结构化研究任务非思考模式；有对象 schema 时用 JSON object |
| OpenAI GPT-4o mini | Chat Completions，max_completion_tokens；允许 temperature；已有任务 schema 使用 JSON schema |
| OpenAI GPT-5 mini | max_completion_tokens，省略 temperature；使用 minimal reasoning 配置，schema 单独传递 |
| Anthropic Sonnet 5.5 | 原生 Messages，system 与消息分开；max_tokens；省略采样参数；between_tools；output_config.format schema |
| Anthropic 其他已列预设 | Messages，省略不适用采样参数；未强制无依据的思考开关；按预设处理结构输出 |
| 未知自定义模型 | 使用对应厂商协议的最小参数，省略未核对的采样/思考/原生 schema 参数 |

screen 的列表结果通过 items 对象承载，适配对象型结构化输出后再还原；本地 ID/schema 校验继续生效。不同厂商没有无条件接收相同参数集合。没有自动在请求失败后换模型、换账户或退回 mock。

来源：[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、[GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini)、[GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini)、[Claude 模型总览](https://platform.claude.com/docs/en/models/overview)、[Claude Sonnet 参数](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)、[Claude 结构化输出](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)、[DeepSeek API](https://api-docs.deepseek.com/api/create-chat-completion/)。本地离线通过不替代各厂商实际账户验证。

## 脱敏诊断

研究模型请求、模型列表请求和验证请求记录到 `.research_runs/api_diagnostics/events.jsonl`（已 gitignore）。字段包括 provider、去除认证/查询参数的 base URL、模型显示名、实际 API ID、实际 HTTP 状态（未知则空）、错误类别、脱敏后的服务商错误信息/代码/参数、耗时、已返回的用量和请求控制参数。

界面提供“请求诊断（已脱敏）”。认证、权限、余额、额度、限流、参数、网络、超时、模型不可用与接口路径错误分别处理；不把所有 404 或失败都解释为模型 ID 错误。错误中返回的原始 Key、Bearer token、请求 messages/headers/prompt 不写入日志。测试日志另存，标识 offline_test，不能当真实验证结果。

`record_event` 写入失败不影响模型请求本身；诊断文件不应被当作进程恢复机制或完整账单。实际验证的完整脱敏结果见随附 JSON。

## 离线检查

**55 项测试通过**，覆盖已有研究流程、三家实际 SDK 的合成请求/响应序列化、模型切换、参数差异、错误 ID、无权限、限流、参数不兼容、Key 隔离/脱敏、mock 不通过、收费提示与明确确认、元数据成功不等于生成成功、列表失败不阻止配置、CLI 编号流程和旧界面状态迁移。

```powershell
$env:MOCK_MODE="1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

compileall、git diff --check 通过。测试合成 HTTP 请求不算真实厂商验证；原 `.env` 与历史评测数据未修改，未提交、推送或部署。

## 关于耗时

不同模型的推理模式、响应速度和输出长度会影响问题分解、相关性筛选及报告生成；来源 API 的等待/限流、补充轮次、全文获取、解析与本地 embedding 也会影响总时长。本次 3.379 秒是极小生成探针，不是一次文献任务的时间，不应据此外推提速比例。

下一步可以结合现有 telemetry.stages、search_events 和本轮 API 请求秒数，分别测量搜索、模型筛选、全文处理和写作阶段，再决定缓存、减少重复判断或受限并发等优化。本轮没有把更换模型作为全部性能问题的结论。
