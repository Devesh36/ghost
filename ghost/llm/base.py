from __future__ import annotations

from typing import Protocol, Any


class LLMProvider(Protocol):
    async def generate(self, system: str, prompt: str) -> str: ...
    async def tool_call(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class FakeProvider:
    """Deterministic, injectable responses for tests and offline demos."""

    def __init__(self, responses: list[dict[str, Any]]):
        self.responses = iter(responses)
        self.calls: list[tuple[str, str]] = []

    async def generate(self, system: str, prompt: str) -> str:
        import json
        return json.dumps(await self.tool_call(system, prompt, {}))

    async def tool_call(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((system, prompt))
        return next(self.responses)
