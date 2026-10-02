"""Keep the OpenSRE-style dependency direction enforceable as Ghost grows."""
import ast
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = {
    'surfaces': {'surfaces', 'bootstrap', 'core', 'infrastructure', 'config'},
    'bootstrap': {'bootstrap', 'core', 'infrastructure', 'config'},
    'core': {'core', 'infrastructure', 'config'},
    'infrastructure': {'infrastructure', 'core', 'config'},
    'config': {'config'},
}


def test_first_party_imports_follow_layer_boundaries():
    violations = []
    for layer, allowed in LAYERS.items():
        for path in (ROOT / layer).rglob('*.py'):
            module = '.'.join(path.relative_to(ROOT).with_suffix('').parts)
            package = module.rsplit('.', 1)[0]
            for node in ast.walk(ast.parse(path.read_text())):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    name = node.module or ''
                    if node.level:
                        name = resolve_name('.' * node.level + name, package)
                    imports = [name, *[f'{name}.{alias.name}' for alias in node.names]]
                for imported in imports:
                    target = imported.split('.')[0]
                    if target == 'ghost' or (target in LAYERS and target not in allowed):
                        violations.append(f'{module}:{node.lineno} imports {imported}')
                    for surface, peer in [('cli', 'interactive_shell'), ('interactive_shell', 'cli')]:
                        if module.startswith(f'surfaces.{surface}.') and imported.startswith(f'surfaces.{peer}'):
                            violations.append(f'{module}:{node.lineno} imports peer {imported}')
    assert not violations, '\n'.join(violations)
