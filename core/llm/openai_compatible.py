from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field
from infrastructure.safety.masking.model_input import validate_model_input


class ProviderError(RuntimeError):
    """Safe to persist: never includes response bodies, prompts, or endpoint URLs."""


class ProviderLimits(BaseModel):
    request_timeout: float = Field(default=60, gt=0, le=300, allow_inf_nan=False)
    request_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)
    response_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _json(text: str | bytes) -> Any:
    try:
        # Python's decoder accepts NaN/Infinity by default; these are not JSON.
        return json.loads(text, parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ProviderError("Provider returned invalid JSON.") from None


class OpenAICompatibleProvider:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None,
                 *, limits: ProviderLimits | None = None):
        self.api_key = api_key or os.getenv("GHOST_API_KEY")
        self.base_url = (base_url or os.getenv("GHOST_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("GHOST_MODEL")
        self.limits = limits or ProviderLimits()
        if not self.api_key or not self.model:
            raise ValueError("Set GHOST_API_KEY and GHOST_MODEL to use AI reasoning")

    async def generate(self, system: str, prompt: str) -> str:
        validate_model_input(system, prompt, credentials=(self.api_key,))
        payload = json.dumps({"model": self.model, "messages": [{"role": "system", "content": system},
            {"role": "user", "content": prompt}], "temperature": 0}, ensure_ascii=False).encode("utf-8")
        if len(payload) > self.limits.request_bytes:
            raise ProviderError("Model request exceeds the configured byte limit.")
        try:
            # HTTPX timeouts bound idle operations. This outer deadline also bounds
            # servers which keep sending small chunks indefinitely.
            async with asyncio.timeout(self.limits.request_timeout):
                async with httpx.AsyncClient(timeout=self.limits.request_timeout, follow_redirects=False) as client:
                    async with client.stream("POST", f"{self.base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                                     "Accept-Encoding": "identity"}, content=payload) as response:
                        if response.status_code != 200:
                            raise ProviderError(f"Model request failed (HTTP {response.status_code}).")
                        # Refuse compression rather than decompressing unbounded input
                        # before checking its decoded size.
                        if response.headers.get("content-encoding", "identity").lower() != "identity":
                            raise ProviderError("Provider response must use identity content encoding.")
                        declared = response.headers.get("content-length")
                        if declared is not None:
                            try:
                                size = int(declared)
                            except ValueError:
                                raise ProviderError("Provider sent an invalid content length.") from None
                            if size < 0 or size > self.limits.response_bytes:
                                raise ProviderError("Provider response exceeds the configured byte limit.")
                        body = bytearray()
                        async for chunk in response.aiter_raw():
                            if len(body) + len(chunk) > self.limits.response_bytes:
                                raise ProviderError("Provider response exceeds the configured byte limit.")
                            body.extend(chunk)
        except (TimeoutError, httpx.TimeoutException):
            raise ProviderError("Model request exceeded its deadline.") from None
        except httpx.HTTPError:
            raise ProviderError("Model request failed during HTTP transport.") from None
        data = _json(bytes(body))
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") != "stop" or not isinstance(content, str) or not content.strip():
                raise ValueError
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            raise ProviderError("Provider returned an incomplete or invalid completion.") from None
        return content

    async def tool_call(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        result = (await self.generate(system + "\nReturn only a JSON object matching this schema: " + json.dumps(schema), prompt)).strip()
        if result.startswith("```") and result.endswith("```") and "\n" in result:
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        data = _json(result)
        if not isinstance(data, dict):
            raise ProviderError("Provider tool response must be a JSON object.")
        return data
