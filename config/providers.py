"""Public connection choices; no credentials, models or account state."""
CONNECTION_CHOICES = {
    'codex': 'Codex CLI login / optional --model',
    'claude-code': 'Claude Code login / optional --model',
    'claude': 'Claude API / --model and ANTHROPIC_API_KEY',
    'openai': 'OpenAI API / --model and OPENAI_API_KEY',
    'compatible': 'Compatible API / --model, --base-url and key variable',
    'openrouter': 'OpenRouter API / --model and OPENROUTER_API_KEY',
    'ollama': 'Local Ollama / --model; no API key by default',
}
