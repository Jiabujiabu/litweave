# DeepSeek ModelCallError 修复

日期：2026-10-31（America/Chicago）。用户配置：DeepSeek / deepseek-chat。

## 已确认与未确认

- 之前的默认模型名 deepseek-chat 已过时。当前官方 Chat Completions 文档列出 deepseek-flash 和 deepseek-v4-pro；官方更新日志曾公告旧 deepseek-chat / deepseek-reasoner 停用。这是明确的配置缺陷。
- 旧实现把所有模型异常归为同一个 ModelCallError，网页又只显示类名，导致无法判断具体错误。已修复。
- 没有取得用户这次请求的原始 HTTP 状态，也没有使用其 Key 发起测试，因此不声称已确认该账户的 Key、余额或权限正常。

来源：[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[官方更新日志](https://api-docs.deepseek.com/updates/)、[错误码](https://api-docs.deepseek.com/quick_start/error_codes/)。

## 修改

1. 移除首页 “This app never uses the operator's key.” 及对应中文文案，精简侧边栏说明。用户自带 Key 的调用边界保持有效。
2. DeepSeek 新会话默认模型改为 deepseek-flash；.env.example 同步。未修改用户的 .env。
3. 已输入旧模型名的会话不被静默替换；显示“改用 deepseek-flash”按钮，点击确认后保留同一服务商的用户 Key。
4. DeepSeek 结构化任务显式设置 thinking disabled，延续旧 chat 非思考行为，避免默认思考消耗输出预算后没有有效正文。
5. 异常按认证、余额、权限、模型不可用、限流、额度、超时、连接、请求参数、SDK 兼容性等分类。界面显示安全说明与 HTTP 状态码，不显示原始响应、密钥或提示词。
6. 增加“检查连接与模型”：使用当前用户 Key 获取模型列表；DeepSeek 另尝试获取余额是否可用的布尔状态，不保存金额。未调用文本生成接口。模型可见不代表实际生成必然有权限或额度。
7. CLI 同样显示安全的具体错误，不再只给 ModelCallError 类名。

## 使用

重启一次 Streamlit 后台，刷新页面：

```powershell
cd path/to/academic-research-agent
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

选择 DeepSeek，模型填 deepseek-flash，输入自己的官方 API Key，然后点击“检查连接与模型”。如页面仍保留 deepseek-chat，先点击“改用 deepseek-flash”。通过后再开始研究。

出现 HTTP 401 时核对 Key 和接口平台是否匹配；HTTP 402 表示 DeepSeek API 余额不足；其他错误会显示对应的可操作原因。不需要提供或发送 API Key，只需后续反馈安全的错误提示即可。

## 验证

- **41 项离线测试通过**（原 33 项 + 8 项模型/错误/界面回归）。
- 覆盖旧模型预检、显式切换不丢 Key、DeepSeek 非思考参数、真实 SDK 合成 HTTP 错误分类、Key 和原始错误体不泄露、连接检查仅 GET 元数据/余额，以及网页真实模式显示 HTTP 原因。
- compileall 和 git diff --check 通过。
- 无真实模型调用、无付费测试、未提交、未推送、未部署。
