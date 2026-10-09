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


def test_core_does_not_import_terminal_frameworks():
    violations = []
    terminal_packages = {'rich', 'typer', 'click', 'prompt_toolkit'}
    for path in (ROOT / 'core').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                if name.split('.')[0] in terminal_packages:
                    violations.append(f'{path.relative_to(ROOT)}:{node.lineno} imports {name}')
    assert not violations, '\n'.join(violations)


def test_domain_models_do_not_import_runtime_layers():
    violations = []
    for path in (ROOT / 'core' / 'domain').rglob('*.py'):
        module = '.'.join(path.relative_to(ROOT).with_suffix('').parts)
        for node in ast.walk(ast.parse(path.read_text())):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            if isinstance(node, ast.ImportFrom):
                name = node.module or ''
                if node.level:
                    name = resolve_name('.' * node.level + name, module.rsplit('.', 1)[0])
                names.append(name)
            for name in names:
                if name.split('.')[0] in LAYERS and not name.startswith('core.domain'):
                    violations.append(f'{module}:{node.lineno} imports {name}')
    assert not violations, '\n'.join(violations)
