"""Trusted, bounded helper-level probe, executed only inside OS confinement."""
import ast
import json
from pathlib import Path
import sys
from core.security.repair import parser_function
from infrastructure.security.bandit import source_bytes


def probe(path: str, patched: bool) -> dict:
    source = source_bytes(Path.cwd(), path).decode('utf-8')
    function = parser_function(source, patched=patched)
    namespace = {}
    exec(compile(ast.parse(source), '<validated-parser>', 'exec'), namespace)
    parse = namespace[function.name]
    literals = [('42', 42), ('[1, 2]', [1, 2]), ('{"enabled": True}', {'enabled': True})]
    preserved = all(parse(text) == value for text, value in literals)
    try:
        evaluated = parse("__import__('builtins').sum([19, 23])") == 42
        rejected = False
    except (ValueError, SyntaxError):
        evaluated, rejected = False, True
    return {'literal_cases': len(literals), 'literals_preserved': preserved,
            'function_call_executed': evaluated, 'function_call_rejected': rejected}


if __name__ == '__main__':
    print(json.dumps(probe(sys.argv[1], sys.argv[2] == 'patched')))
