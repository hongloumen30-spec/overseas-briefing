"""TokenHub -> Claude exact-text MCP App; local/source-only until hosted.
Never expose the MCP endpoint without HTTPS and access controls.
"""
from pathlib import Path
from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from tokenhub_chat import chat_completion

UI_RESOURCE_URI = "ui://tokenhub-claude/answer.html"
apps = Apps()

@apps.tool(
    resource_uri=UI_RESOURCE_URI,
    name="ask_claude_opus",
    title="向 Claude Opus 4.7 提问（原文显示）",
    description=(
        "把问题发给 TokenHub claude-opus-4-7-stable 模型，返回未经改写的回复原文。"
        "MCP App 直接显示工具结果，避免由 GPT 复述。仅在用户明确请求时调用外部模型。"
    ),
)
def ask_claude_opus(question: str) -> str:
    """Return choices[0].message.content verbatim, including whitespace."""
    if not question.strip():
        raise ValueError("问题不能为空")
    return chat_completion([{"role": "user", "content": question}])

apps.add_html_resource(
    UI_RESOURCE_URI,
    (Path(__file__).parent / "answer.html").read_text(encoding="utf-8"),
    title="Claude Opus 原文",
)
mcp = MCPServer("TokenHub Claude Opus", extensions=[apps])

if __name__ == "__main__":
    # Local development only, not publicly exposed.
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000,
            stateless_http=True, json_response=True)
