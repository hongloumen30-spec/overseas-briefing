# Claude Opus 原文直通 MCP App

## 当前状态（2026-11-10）

**代码已经能够在受保护的 Web 服务上运行，尚未部署，也尚未连接 ChatGPT；没有使用真实 TokenHub Key 发起请求。**

注意：OpenAI 目前的官方说明将 **自定义 MCP 服务的完整连接权限** 主要提供给 **Business / Enterprise / Edu**；Pro 的自定义 MCP 连接能力有限，Plus 并不能据此保证可以把这个自建服务接进聊天窗口。不能因为创建了 Python 服务或 ZIP，就声称 Plus 可以直接使用它。请以实际账户的插件页面和平台权限为准。

## 工作原理

- `tokenhub_chat.py` 固定调用 `claude-opus-4-7-stable` 的 Chat Completions。
- `ask_claude_opus(question)` 将 `choices[0].message.content` **按原字符串返回**。
- MCP App 使用 `textContent` 和 `white-space: pre-wrap` 显示工具结果，不让 GPT 替代 Claude 写回复。
- 这里的“原文”指 **TokenHub 返回的可见文本字段**，不是 Claude 未公开的推理过程。若客户端只呈现工具结果为 GPT 文本，仍不能保证 GPT 不改变格式。
- 因为是外部 API，**TokenHub 可能按调用计费**，与 ChatGPT Plus 订阅分开。

## 免费托管预备配置（未部署）

项目根目录准备了 `render.yaml`，可作为 Render **Free** Web Service 的 Blueprint。Render 免费服务空闲时休眠，首次唤醒可能很慢；并有免费时数和网络流量用量限制，**不能承诺任何情形下绝对零成本**。

托管需要在 Render 的**密钥设置**中配置 **两把不同的密钥**：

1. `TOKENHUB_API_KEY`：新生成的 TokenHub API Key，仅供服务器调用上游接口；
2. `MCP_ACCESS_TOKEN`：**独立生成至少 32 字符**的随机访问令牌，用于保护本服务。

两者不可混用。任何一个都**不能**写到 `render.yaml`、Git 仓库、聊天消息或浏览器前端代码。

独立生成 MCP 访问令牌（在自己电脑运行并私下保存）：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Render 会自动提供 `RENDER_EXTERNAL_HOSTNAME`，服务的 Host allowlist 将使用这一环境变量。已在 ASGI 边界实现独立 Bearer 鉴权、每分钟有限请求数、防止外部随意消耗 TokenHub 额度。健康检查 `/health` 不含任何私密信息。

托管平台启动命令是：

```bash
uvicorn tokenhub_mcp.asgi:app --host 0.0.0.0 --port $PORT --proxy-headers
```

服务端 MCP 路径预期为 `https://<你自己的域名>/mcp`；**必须先部署成功**，该地址才会存在。

## 离线测试

```bash
python -m pip install -r tokenhub_mcp/requirements.txt
python -m unittest discover -s tokenhub_mcp/tests -v
python -m unittest -v test_tokenhub_chat.py
```

本地开发模式（只监听 localhost）：

```bash
python -m tokenhub_mcp.server
```

如需本地测试带鉴权的服务，应先在自己终端设置 `MCP_ACCESS_TOKEN` 后执行：

```bash
uvicorn tokenhub_mcp.asgi:app --host 127.0.0.1 --port 8000
```

## 上线和连接的条件

1. 轮换曾在聊天记录中暴露的旧 TokenHub Key。
2. 连接可信赖的托管平台并在其安全环境变量里添加新密钥。
3. 完成远端 MCP 的 HTTPS 联通性、鉴权、API 计费与端到端测试。
4. **检查你的 ChatGPT 账户是否具备自定义 MCP 连接权限**。如没有，不能通过 ZIP 或仓库代码绕过产品限制；可以在独立网页中使用同一个接口。
5. 即使支持 MCP 工具连接，也要确认具体客户端支持 MCP Apps 原文组件，否则原文可能仍被聊天模型加工。

本项目未替你购买付费服务，没有部署，也没有替你向 TokenHub 消费额度。
