# Claude Opus 原文直通 MCP App

**当前状态：只有源码和离线验证；尚未部署、尚未连接到 ChatGPT，也未实际测试 TokenHub 在线推理。**

## 原理

- 调用 `tokenhub_chat.py`，固定模型为 `claude-opus-4-7-stable`。
- MCP 工具 `ask_claude_opus(question)` 返回 API 的 `choices[0].message.content` 原始字符串，不作总结、润色或 Markdown 转换。
- 聊天内 MCP App 使用 DOM `textContent` 和 CSS `white-space: pre-wrap` 直接呈现原文。
- 即使聊天里的 GPT 最终总结了工具结果，独立组件仍显示收到的原文。ChatGPT 是否实际呈现取决于宿主对 MCP App 的支持。
- 这**不会切换 ChatGPT 底层模型**，只是把 Claude 作为一个外部工具。

## 离线验证

从仓库根目录运行（Python 3.11+）：

```bash
python -m pip install "mcp>=2,<3" requests
python -m unittest discover -s tokenhub_mcp/tests -v
```

## 本地启动

把 `TOKENHUB_API_KEY` 安全地写入本机环境变量，而非代码或 Git。执行：

```bash
python -m tokenhub_mcp.server
```

开发服务默认绑定 `127.0.0.1:8000/mcp`，不会对外暴露。手机端 ChatGPT 不能直接连接这个仅本机可见的地址。

## 后续上线条件

1. 需要一个实际可用、支持 Streamable HTTP / MCP Apps 的托管环境。
2. 必须设置 HTTPS、严格身份认证和限流，**绝不能直接暴露未鉴权的 MCP 服务**，否则他人可消耗模型额度。
3. 在服务端秘密管理中设置**新生成**的 `TOKENHUB_API_KEY`；不要暴露在网页 JavaScript、GitHub 或聊天记录中。
4. 托管成功并拿到真实的 `https://.../mcp` 地址后，才可以创建真正可调用的 ChatGPT MCP 插件。
5. 在线测试后才能确认 TokenHub 接口通畅、密钥有效、账户有额度及 UI 原文呈现准确。

**重要：** 先前暴露在聊天中的旧密钥建议立即撤销并轮换。这里没有保存或使用那把密钥。
