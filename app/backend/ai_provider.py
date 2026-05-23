from __future__ import annotations

import json
import socket
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse


DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"


def call_openai_compatible(
    payload: dict[str, Any],
    api_key: str,
    *,
    base_url: str | None = None,
    timeout: int = 180,
) -> Any:
    if not api_key:
        raise ValueError("API key is required.")
    url = _normalize_chat_completions_url(base_url)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise ValueError(
                "模型服务鉴权失败：请确认 API key、Base URL 和 Model 属于同一服务商，"
                "且 key 未过期、未禁用、额度可用。"
            ) from exc
        raise ValueError(f"模型服务请求失败：HTTP {exc.code}，请检查 Base URL 和模型名。") from exc
    except URLError as exc:
        raise ValueError("模型服务连接失败：请检查 Base URL、网络或代理设置。") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ValueError(
            "模型服务响应超时：这通常是模型生成较慢、网络不稳定或服务商繁忙。"
            "请稍后重试，或减少选择的知识块数量、换用更快模型。"
        ) from exc
    return body


def _normalize_chat_completions_url(base_url: str | None) -> str:
    if not base_url:
        return DEFAULT_BASE_URL
    value = str(base_url).strip().rstrip("/")
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Base URL 必须是完整地址，例如 https://api.openai.com/v1")
    if parsed.path.endswith("/chat/completions"):
        return value
    if parsed.path.endswith("/v1"):
        return f"{value}/chat/completions"
    if parsed.path in {"", "/"}:
        return f"{value}/v1/chat/completions"
    return f"{value}/chat/completions"
