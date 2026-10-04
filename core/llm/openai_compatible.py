from __future__ import annotations

import os

from core.llm.transport import JSONTools, ProviderError, ProviderLimits, post_json
from infrastructure.safety.masking.model_input import validate_model_input


class OpenAICompatibleProvider(JSONTools):
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
        data = await post_json(f"{self.base_url}/chat/completions",
                               {"Authorization": f"Bearer {self.api_key}"},
                               {"model": self.model, "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": prompt}]}, self.limits)
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") != "stop" or not isinstance(content, str) or not content.strip():
                raise ValueError
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            raise ProviderError("Provider returned an incomplete or invalid completion.") from None
        return content
