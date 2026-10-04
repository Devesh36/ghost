"""Shared bounded model transport; errors never contain payloads or credentials."""
import asyncio
import json
from typing import Any

import httpx
from pydantic import BaseModel, Field


class ProviderError(RuntimeError):
    pass


class ProviderLimits(BaseModel):
    request_timeout: float = Field(default=60, gt=0, le=300, allow_inf_nan=False)
    request_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)
    response_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)


def _reject_constant(value: str) -> None:
    raise ValueError('Non-finite JSON number')


def parse_json(text: str | bytes) -> Any:
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ProviderError('Provider returned invalid JSON.') from None


async def post_json(url: str, headers: dict, data: dict, limits: ProviderLimits) -> Any:
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    if len(payload) > limits.request_bytes:
        raise ProviderError('Model request exceeds the configured byte limit.')
    try:
        async with asyncio.timeout(limits.request_timeout):
            async with httpx.AsyncClient(timeout=limits.request_timeout, follow_redirects=False) as client:
                async with client.stream('POST', url, headers={**headers, 'Content-Type': 'application/json',
                                         'Accept-Encoding': 'identity'}, content=payload) as response:
                    if response.status_code != 200:
                        raise ProviderError(f'Model request failed (HTTP {response.status_code}).')
                    if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                        raise ProviderError('Provider response must use identity content encoding.')
                    declared = response.headers.get('content-length')
                    if declared is not None:
                        try:
                            size = int(declared)
                        except ValueError:
                            raise ProviderError('Provider sent an invalid content length.') from None
                        if size < 0 or size > limits.response_bytes:
                            raise ProviderError('Provider response exceeds the configured byte limit.')
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(body) + len(chunk) > limits.response_bytes:
                            raise ProviderError('Provider response exceeds the configured byte limit.')
                        body.extend(chunk)
    except (TimeoutError, httpx.TimeoutException):
        raise ProviderError('Model request exceeded its deadline.') from None
    except httpx.HTTPError:
        raise ProviderError('Model request failed during HTTP transport.') from None
    return parse_json(bytes(body))


class JSONTools:
    async def tool_call(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        result = (await self.generate(system + '\nReturn only a JSON object matching this schema: ' +
                                     json.dumps(schema), prompt)).strip()
        if result.startswith('```') and result.endswith('```') and '\n' in result:
            result = result.split('\n', 1)[1].rsplit('```', 1)[0]
        data = parse_json(result)
        if not isinstance(data, dict):
            raise ProviderError('Provider tool response must be a JSON object.')
        return data
