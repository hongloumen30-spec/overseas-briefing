# 智桥 TokenHub 模型接入

本项目使用 Python 与现有的 `requests` 依赖，通过 **OpenAI Chat Completions** 协议调用 TokenHub。原每日情报脚本不受影响，不会自动产生付费模型请求。

- 显示名称 / model ID：`claude-opus-4-7-stable`
- 分类：文本生成
- SDK Base URL：`https://api.tokenhub.paper2ppt.work/v1`
- POST：`https://api.tokenhub.paper2ppt.work/v1/chat/completions`
- 鉴权：`Authorization: Bearer <API_KEY>`
- 密钥来源：仅 `TOKENHUB_API_KEY` 环境变量
- 第一阶段：非流式文本生成；暂不启用工具调用、流式传输和多模态。

## 本地使用

已有环境安装了 `requests` 时无需额外安装：

```bash
python -m pip install requests
```

在终端**本地**设置环境变量（不要把密钥粘贴到聊天、脚本或 Git 中）。

Linux / macOS：

```bash
export TOKENHUB_API_KEY='这里填写你自己的密钥'
python tokenhub_chat.py --prompt '请只回复：连接成功'
```

Windows PowerShell：

```powershell
$env:TOKENHUB_API_KEY = '这里填写你自己的密钥'
python tokenhub_chat.py --prompt '请只回复：连接成功'
```

预期：打印模型返回的文本。若配置错误，输出明确的 HTTP 状态提示，并以非零状态码退出。命令会发起真实 API 请求，可能产生 TokenHub 费用。

在项目其他 Python 模块中调用：

```python
from tokenhub_chat import chat_completion

result = chat_completion([{"role": "user", "content": "你好"}])
print(result)
```

## 离线最小验证

不需要密钥、不会发起网络请求：

```bash
python -m unittest -v test_tokenhub_chat.py
```

覆盖：模型 ID 与 endpoint、请求非流式、Bearer 鉴权、缺失密钥、401/402/429/502、限次指数退避、网络错误脱敏。

## 重要安全说明

不要在源码、日志、PR 或提交历史中存储密钥。`.gitignore` 排除 `.env`。如果在 GitHub Actions 中使用，请把密钥放进仓库 Actions Secrets（名称：`TOKENHUB_API_KEY`），并只传给真正需要调用 API 的步骤。不要向不受信任的 Pull Request 暴露 Secrets。

HTTP 429 和 5xx 最多重试 2 次（共最多 3 次请求），间隔为 0.5 秒、1 秒；401 和 402 不重试。当前仅验证协议适配，真实请求能否成功还取决于有效的密钥、账户额度以及服务端模型是否开放。
