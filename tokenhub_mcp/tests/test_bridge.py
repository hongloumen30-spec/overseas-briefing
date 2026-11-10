"""Offline MCP bridge tests: never send a real request or log a credential."""
import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from tokenhub_mcp.server import UI_RESOURCE_URI, ask_claude_opus, mcp

class BridgeTests(unittest.TestCase):
    def test_verbatim_response_and_question(self):
        original = "标题：测试\n\n第一段。  🐱\n\n> 原文不变。\n"
        with patch("tokenhub_mcp.server.chat_completion", return_value=original) as api:
            answer = ask_claude_opus("请测试")
        self.assertEqual(answer, original)
        api.assert_called_once_with([{"role": "user", "content": "请测试"}])

    def test_blank_question_rejected(self):
        with self.assertRaisesRegex(ValueError, "问题不能为空"):
            ask_claude_opus("   ")

    def test_mcp_tool_declares_exact_ui(self):
        tools = asyncio.run(mcp.list_tools())
        bound = next(t for t in tools if t.name == "ask_claude_opus")
        self.assertEqual(bound.meta["ui"]["resourceUri"], UI_RESOURCE_URI)

    def test_ui_uses_text_content_preformatted(self):
        html = (Path(__file__).parent.parent / "answer.html").read_text(encoding="utf-8")
        self.assertIn('node.textContent = block ? block.text', html)
        self.assertIn('white-space: pre-wrap', html)
        self.assertIn('ui/notifications/tool-result', html)

if __name__ == "__main__":
    unittest.main()
