#!/usr/bin/env python3
"""Minimal, non-streaming TokenHub OpenAI Chat Completions client.

Credentials are read exclusively from TOKENHUB_API_KEY at request time.
"""

import argparse
import os
import sys
import time
from typing import Callable, Optional

import requests

MODEL_ID = "claude-opus-4-7-stable"
BASE_URL = "https://api.tokenhub.paper2ppt.work/v1"
CHAT_COMPLETIONS_URL = f"{BASE_URL}/chat/completions"


class TokenHubError(RuntimeError):
    """Safe, user-facing TokenHub failure (never contains credentials)."""


def _status_message(status: int) -> str:
    if status == 401:
        return "401 未授权：请检查 TOKENHUB_API_KEY 是否正确或已过期。"
    if status == 402:
        return "402 余额或额度不足：请检查 TokenHub 账户的计费状态。"
    if status == 429:
        return "429 请求过于频繁或已达到速率限制：稍后再试。"
    if status == 502:
        return "502 TokenHub 上游网关错误：服务暂时不可用，请稍后重试。"
    if 500 <= status <= 599:
        return f"{status} TokenHub 服务端错误：请稍后重试。"
    return f"TokenHub 请求失败（HTTP {status}）：请检查请求参数和账户权限。"


def chat_completion(
    messages: list[dict[str, str]],
    *,
    timeout: float = 30,
    max_retries: int = 2,
    session: Optional[requests.Session] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Return assistant text; retry 429/5xx at most `max_retries` times."""
    key = os.environ.get("TOKENHUB_API_KEY", "").strip()
    if not key:
        raise TokenHubError("缺少 TOKENHUB_API_KEY：请先设置环境变量（不要写进源码）。")
    if not messages:
        raise TokenHubError("messages 不能为空。")
    if max_retries < 0:
        raise ValueError("max_retries 不能为负数")

    payload = {"model": MODEL_ID, "messages": messages, "stream": False}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    http = session if session is not None else requests

    for attempt in range(max_retries + 1):
        try:
            response = http.post(
                CHAT_COMPLETIONS_URL, headers=headers, json=payload, timeout=timeout
            )
        except requests.RequestException:
            # Do not interpolate exception details (may contain request metadata).
            raise TokenHubError("TokenHub 网络连接失败：请检查网络、代理与接口地址。") from None

        status = response.status_code
        if 200 <= status < 300:
            try:
                content = response.json()["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("non-text content")
                return content
            except (ValueError, KeyError, IndexError, TypeError):
                raise TokenHubError("TokenHub 响应格式异常：没有找到文本内容。") from None

        if (status == 429 or 500 <= status <= 599) and attempt < max_retries:
            sleep(min(0.5 * (2 ** attempt), 4.0))
            continue
        raise TokenHubError(_status_message(status))

    raise AssertionError("Unreachable retry state")


def main() -> int:
    parser = argparse.ArgumentParser(description="TokenHub 非流式 Chat Completions 最小测试")
    parser.add_argument("--prompt", default="请只回复：连接成功")
    args = parser.parse_args()
    try:
        print(chat_completion([{"role": "user", "content": args.prompt}]))
        return 0
    except TokenHubError as exc:
        print(f"[TokenHub] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
