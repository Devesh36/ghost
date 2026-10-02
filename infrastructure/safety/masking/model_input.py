"""Conservative checks on model-bound evidence; not a complete secret scanner."""
from __future__ import annotations

import json
import os
from pathlib import PurePosixPath
import re
from typing import Any

from core.llm.base import LLMProvider


class ModelInputBlocked(ValueError):
    """Contains no source content or secret values; safe for saved run notes."""


_ENV_NAME = re.compile(r'(?:^|_)(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE_KEY|ACCESS_KEY|CREDENTIALS?)(?:_|$)', re.I)
_PRIVATE_KEY = re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----')
_TOKEN = re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b')
_ASSIGNMENT = re.compile(
    r'''(?ix)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret[_-]?key)
        ["']?\s*[:=]\s*["']([^"'\r\n]{8,})["']''')


def sensitive_path(path: str) -> bool:
    parts = [part.casefold() for part in PurePosixPath(path.replace('\\', '/')).parts]
    if any(part in {'.ssh', '.aws', '.azure', '.gnupg', 'gcloud'} for part in parts):
        return True
    if not parts:
        return False
    name = parts[-1]
    return (name == '.env' or name.startswith('.env.') or name in {'.npmrc', '.pypirc', '.netrc',
            'credentials.json', 'service-account.json', 'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519'}
            or name.endswith(('.pem', '.key', '.p12', '.pfx', '.keystore')))


def validate_model_input(*texts: str, credentials: tuple[str, ...] = ()) -> None:
    """Reject a whole request, avoiding placeholder-contaminated patch proposals.

    Only selected patterns and environment values of eight or more characters
    are recognized. Encoded/transformed or unrecognized secrets may evade checks.
    """
    known = {value for name, value in os.environ.items() if _ENV_NAME.search(name) and len(value) >= 8}
    known.update(value for value in credentials if len(value) >= 8)
    forms = set(known)
    for value in known:
        forms.add(json.dumps(value)[1:-1])
        forms.add(json.dumps(value, ensure_ascii=False)[1:-1])
    for text in texts:
        # Evidence often arrives as JSON containing source strings. Check common
        # quoting escapes too, without modifying the request itself.
        unquoted = text.replace('\\"', '"').replace("\\'", "'")
        if any(value in text for value in forms) or _PRIVATE_KEY.search(text) or _TOKEN.search(text) or _ASSIGNMENT.search(unquoted):
            raise ModelInputBlocked('Model request blocked: evidence may contain credentials. '
                                    'No request was sent; deterministic investigation remains available.')


async def checked_tool_call(provider: LLMProvider, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Provider-independent boundary used by every built-in reasoning agent."""
    validate_model_input(system, prompt, json.dumps(schema))
    return await provider.tool_call(system, prompt, schema)
