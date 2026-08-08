from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from app.clients.deepseek import DeepSeekClient
from app.core.config import Settings


def mock_deepseek_client(
    content: str,
    capture: Callable[[httpx.Request], None] | None = None,
    status_code: int = 200,
) -> DeepSeekClient:
    """Provide a transport-level DeepSeek simulation; production code remains unchanged."""

    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture(request)
        if status_code != 200:
            return httpx.Response(status_code, json={"error": {"message": "test provider error"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_base_url="https://mock.deepseek.local",
        deepseek_model="test-model",
    )
    return DeepSeekClient(settings, transport=httpx.MockTransport(handler))


def ai_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "category": "NETWORK",
        "priority": "P2",
        "summary": "内网连接异常",
        "reason": "描述表明客户端无法访问内网资源。",
        "injection_detected": False,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)

