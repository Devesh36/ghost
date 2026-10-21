"""Independent Node TLS switch candidates and safe neighboring assignments."""
import subprocess

from infrastructure.security.bandit import audit_repository


def tls_cases():
    cases = {
        'existing_options.js': ('const options = {rejectUnauthorized: false};', True),
        'safe_options.js': ('const options = {rejectUnauthorized: true};', False),
        'enabled.js': ('process.env.NODE_TLS_REJECT_UNAUTHORIZED = "1";', False),
        'true_string.js': ('process.env.NODE_TLS_REJECT_UNAUTHORIZED = "true";', False),
        'empty.js': ('process.env.NODE_TLS_REJECT_UNAUTHORIZED = "";', False),
        'false_string.js': ('process.env.NODE_TLS_REJECT_UNAUTHORIZED = "false";', False),
        'false_boolean.js': ('process.env.NODE_TLS_REJECT_UNAUTHORIZED = false;', False),
        'true_boolean.js': ('process.env.NODE_TLS_REJECT_UNAUTHORIZED = true;', False),
        'unknown.js': ('process.env.NODE_TLS_REJECT_UNAUTHORIZED = setting;', False),
        'comparison.js': ('if (process.env.NODE_TLS_REJECT_UNAUTHORIZED === "0") report();', False),
        'different_flag.js': ('process.env.OTHER_TLS_SETTING = "0";', False),
        'unrelated_env.js': ('const config = {env: {}}; config.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'comment.js': ('// process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'string.js': ('const help = `process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";`;', False),
        'shadowed_parameter.js': ('function configure(process) { process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"; }', False),
        'shadowed_local.js': ('const process = {env: {}}; process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'shadowed_let.js': ('let process = {env: {}}; process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'shadowed_var.js': ('var process = {env: {}}; process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'shadowed_arrow.js': ('const configure = process => process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'shadowed_arrow_args.js': ('const configure = (input, process) => { process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"; };', False),
        'shadowed_expression.js': ('const configure = function(process) { process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"; };', False),
        'unrelated_import.js': ('import process from "another-package"; process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'unrelated_namespace.js': ('import * as process from "another-package"; process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'unrelated_named.js': ('import { process } from "another-package"; process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'unrelated_alias.js': ('import { runtime as process } from "another-package"; process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'shadowed_module.js': ('import runtime from "node:process"; function configure(runtime) {runtime.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";}', False),
        'shadowed_env.js': ('import {env as settings} from "node:process"; function configure(settings) {settings.NODE_TLS_REJECT_UNAUTHORIZED = "0";}', False),
        'shadowed_named_env.js': ('import {env} from "node:process"; function configure(env) {env.NODE_TLS_REJECT_UNAUTHORIZED = "0";}', False),
        'shadowed_destructured_env.js': ('const {env} = require("process"); function configure(env) {env.NODE_TLS_REJECT_UNAUTHORIZED = "0";}', False),
        'unrelated_env_alias.js': ('import {env as settings} from "node:process"; const env = {}; env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
        'similarly_named_module.js': ('import runtime from "process-helper"; runtime.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', False),
    }
    for extension in ('js', 'ts'):
        for label, value in (('single', "'0'"), ('double', '"0"'), ('number', '0')):
            cases[f'{label}.{extension}'] = (f'process.env.NODE_TLS_REJECT_UNAUTHORIZED = {value};', True)
        cases[f'brackets.{extension}'] = ('process["env"]["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";', True)
        cases[f'nested.{extension}'] = ('function configure() { process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"; }', True)
    for module in ('process', 'node:process'):
        prefix = 'node' if module.startswith('node:') else 'plain'
        bindings = {
            'default': (f'import runtime from "{module}";', 'runtime.env'),
            'process_name': (f'import process from "{module}";', 'process.env'),
            'namespace': (f'import * as runtime from "{module}";', 'runtime.env'),
            'const': (f'const runtime = require("{module}");', 'runtime.env'),
            'let': (f'let runtime = require("{module}");', 'runtime.env'),
            'var': (f'var runtime = require("{module}");', 'runtime.env'),
            'env_named': (f'import {{env}} from "{module}";', 'env'),
            'env_alias': (f'import {{env as settings}} from "{module}";', 'settings'),
            'env_destructured': (f'const {{env}} = require("{module}");', 'env'),
            'env_renamed': (f'const {{env: settings}} = require("{module}");', 'settings'),
        }
        for extension in ('js', 'ts'):
            for name, (binding, target) in bindings.items():
                for label, value, positive in (('off', '"0"', True), ('numeric', '0', True), ('on', '"1"', False)):
                    cases[f'{prefix}_{name}_{label}.{extension}'] = (
                        f'{binding}\n{target}.NODE_TLS_REJECT_UNAUTHORIZED = {value};', positive)
    return cases


def test_real_tls_switch_detection_and_safe_neighbors(tmp_path, monkeypatch):
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=TLS Rule Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    cases = tls_cases()
    for path, (source, _) in cases.items():
        (tmp_path / path).write_text(source)
    result = audit_repository(tmp_path, javascript=True)
    assert result.status == 'completed', result.notes
    expected = {path for path, (_, positive) in cases.items() if positive}
    actual = {item.path for item in result.findings if item.rule == 'GJS004'}
    assert actual == expected, {'missed': sorted(expected - actual), 'unexpected': sorted(actual - expected)}
    assert len(result.findings) == len(expected)
    assert all(item.state == 'suspected' and item.evidence == 'static' for item in result.findings)
    assert 'process.env' not in result.model_dump_json()
    assert all((tmp_path / path).read_text() == source for path, (source, _) in cases.items())
