"""OpenAI Responses API; stateless requests without server-side response storage."""
import os

from core.llm.transport import JSONTools, ProviderError, ProviderLimits, post_json
from infrastructure.safety.masking.model_input import validate_model_input


class OpenAIResponsesProvider(JSONTools):
    def __init__(self, api_key=None, base_url=None, model=None, *, limits=None):
        self.api_key = api_key or os.getenv('GHOST_API_KEY') or os.getenv('OPENAI_API_KEY')
        self.base_url = (base_url or 'https://api.openai.com/v1').rstrip('/')
        self.model = model or os.getenv('GHOST_MODEL')
        self.limits = limits or ProviderLimits()
        if not self.api_key or not self.model:
            raise ValueError('Set OPENAI_API_KEY and choose a model with ghost connect openai --model <model>.')

    async def generate(self, system: str, prompt: str) -> str:
        validate_model_input(system, prompt, credentials=(self.api_key,))
        data = await post_json(f'{self.base_url}/responses', {'Authorization': f'Bearer {self.api_key}'},
                               {'model': self.model, 'instructions': system, 'input': prompt,
                                'store': False, 'max_output_tokens': 4096}, self.limits)
        try:
            if data['status'] != 'completed':
                raise ValueError
            content = '\n'.join(block['text'] for item in data['output'] if item['type'] == 'message'
                                for block in item['content'] if block['type'] == 'output_text')
            if not content.strip():
                raise ValueError
        except (KeyError, TypeError, AttributeError, ValueError):
            raise ProviderError('Provider returned an incomplete or invalid completion.') from None
        return content
