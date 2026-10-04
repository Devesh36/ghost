"""Claude Messages API adapter using the shared privacy and transport limits."""
import os

from core.llm.transport import JSONTools, ProviderError, ProviderLimits, post_json
from infrastructure.safety.masking.model_input import validate_model_input


class AnthropicProvider(JSONTools):
    def __init__(self, api_key=None, base_url=None, model=None, *, limits=None):
        self.api_key = api_key or os.getenv('GHOST_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
        self.base_url = (base_url or 'https://api.anthropic.com/v1').rstrip('/')
        self.model = model or os.getenv('GHOST_MODEL')
        self.limits = limits or ProviderLimits()
        if not self.api_key or not self.model:
            raise ValueError('Set ANTHROPIC_API_KEY and choose a Claude model with ghost connect claude --model <model>.')

    async def generate(self, system: str, prompt: str) -> str:
        validate_model_input(system, prompt, credentials=(self.api_key,))
        data = await post_json(f'{self.base_url}/messages',
                               {'x-api-key': self.api_key, 'anthropic-version': '2023-06-01'},
                               {'model': self.model, 'system': system, 'messages': [{'role': 'user', 'content': prompt}],
                                'max_tokens': 4096}, self.limits)
        try:
            if data['stop_reason'] != 'end_turn':
                raise ValueError
            content = '\n'.join(block['text'] for block in data['content'] if block['type'] == 'text')
            if not content.strip():
                raise ValueError
        except (KeyError, TypeError, AttributeError, ValueError):
            raise ProviderError('Provider returned an incomplete or invalid completion.') from None
        return content
