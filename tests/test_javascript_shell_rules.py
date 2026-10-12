"""Exercise real imports and safe neighbors, rather than accepting rule syntax."""
import subprocess

from infrastructure.security.bandit import audit_repository


def shell_cases():
    cases = {}
    for module in ('child_process', 'node:child_process'):
        prefix = 'node' if module.startswith('node:') else 'plain'
        bindings = {
            'direct': (f"require('{module}').{{api}}", ''),
            'namespace': ('processes.{api}', f"import * as processes from '{module}';"),
            'default': ('processes.{api}', f"import processes from '{module}';"),
            'named': ('{api}', f"import {{ {{api}}, spawn }} from '{module}';"),
            'alias': ('launch', f"import {{ {{api}} as launch }} from '{module}';"),
        }
        for declaration in ('const', 'let', 'var'):
            bindings[f'{declaration}_module'] = ('processes.{api}', f"{declaration} processes = require('{module}');")
            bindings[f'{declaration}_destructured'] = ('{api}', f"{declaration} {{ {{api}} }} = require('{module}');")
            bindings[f'{declaration}_renamed'] = ('launch', f"{declaration} {{ {{api}}: launch }} = require('{module}');")
        for name, (call, binding) in bindings.items():
            # Test sync/async exec, shell-enabled process APIs and safe argument APIs.
            for api, args, expected in (
                ('exec', 'input', True), ('execSync', 'input', True),
                ('spawn', "'tool', [input], {shell: true}", True),
                ('execFileSync', "'tool', [input], {shell: '/bin/sh'}", True),
                ('spawnSync', "'tool', [input], {shell: false}", False),
                ('execFile', "'tool', [input]", False),
            ):
                # Extra named import uses a different API to keep the fixture valid.
                declaration = binding.replace('{api}', api).replace('spawn, spawn', 'spawn, execFile')
                source = f"{declaration}\n{call.format(api=api)}({args});\n"
                cases[f'{prefix}_{name}_{api}.js'] = (source, expected)
    cases.update({
        'unrelated_object.js': ("const processes = {exec: x => x}; processes.exec(input);", False),
        'unrelated_package.js': ("import {exec as launch} from 'some-other-package'; launch(input);", False),
        'similarly_named_package.js': ("const processes = require('child_process_helpers'); processes.exec(input);", False),
        'comments_and_strings.js': ('// require("child_process").exec(input)\nconst text = "cp.exec(input)";', False),
        'safe_options_variable.js': ("const {spawn} = require('node:child_process'); const options = {shell:false}; spawn('tool', [input], options);", False),
        'typed_alias.ts': ("import {exec as launch} from 'node:child_process'; export const run = (input: string) => launch(input);", True),
        'typed_safe.ts': ("import {spawn} from 'node:child_process'; export const run = (input: string) => spawn('tool', [input], {shell:false});", False),
        'shadowed_namespace.js': ("const processes = require('child_process'); function preview(processes) { processes.exec(input); }", False),
        'shadowed_named.js': ("import {exec as launch} from 'node:child_process'; function preview(launch) { launch(input); }", False),
        'exec_file_shell.js': ("const {execFile} = require('child_process'); execFile('tool', [input], {shell:true});", True),
        'spawn_sync_shell.ts': ("import {spawnSync as launch} from 'node:child_process'; launch('tool', [input], {shell:'/bin/sh'});", True),
    })
    return cases


def test_real_shell_detection_and_safe_neighbors(tmp_path, monkeypatch):
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Shell Rule Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    cases = shell_cases()
    for path, (source, _) in cases.items():
        (tmp_path / path).write_text(source)
    result = audit_repository(tmp_path, javascript=True)
    assert result.status == 'completed', result.notes
    expected = {path for path, (_, positive) in cases.items() if positive}
    actual = {item.path for item in result.findings if item.rule == 'GJS003'}
    assert actual == expected, {'missed': sorted(expected - actual), 'unexpected': sorted(actual - expected)}
    assert len(result.findings) == len(expected)  # Overlapping binding patterns must not duplicate candidates.
    assert all(item.state == 'suspected' and item.evidence == 'static' for item in result.findings)
    assert 'shell: true' not in result.model_dump_json()
    assert all((tmp_path / path).read_text() == source for path, (source, _) in cases.items())
