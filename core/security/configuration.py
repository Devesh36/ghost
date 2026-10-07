"""Versioned identities for recorded static scanner configurations."""
import hashlib
import json
import re


def combined_configuration(profiles: dict[str, str | None]) -> str | None:
    if not profiles or any(not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)
                           for digest in profiles.values()):
        return None
    payload = {'schema': 'ghost-static-configurations-v1', 'engines': profiles}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
