from __future__ import annotations

import json
import os
import httpx
from typing import Any


class OpenAICompatibleProvider:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GHOST_API_KEY")
        self.base_url = (base_url or os.getenv("GHOST_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("GHOST_MODEL")
        if not self.api_key or not self.model:
            raise ValueError("Set GHOST_API_KEY and GHOST_MODEL to use AI reasoning")

    async def generate(self, system: str, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": [{"role": "system", "content": system},
                    {"role": "user", "content": prompt}], "temperature": 0})
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def tool_call(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        result = await self.generate(system + "\nReturn only a JSON object matching this schema: " + json.dumps(schema), prompt)
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(result)
