"""Version and distribution gates must fail before release assets are prepared."""
import hashlib
import io
from pathlib import Path
import tarfile
import zipfile

import pytest

from scripts.release import prepare, safe_member, validate


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'LICENSE').write_text('Independently authored test license fixture\n')
    project = tmp_path / 'pyproject.toml'
    project.write_text('[project]\nname = "ghost-debugger"\nversion = "0.1.0"\nlicense = "MIT"\n')
    return project


@pytest.mark.parametrize('version,prerelease', [('0.1.0', False), ('1.2.3rc1', True),
                                              ('1.0.0a0', True), ('1.0.0b2', True)])
def test_canonical_versions_and_matching_tags(project, version, prerelease):
    project.write_text(project.read_text().replace('0.1.0', version))
    assert validate(project, 'v' + version) == dict(version=version, tag='v' + version, prerelease=prerelease)


@pytest.mark.parametrize('tag', ['v0.2.0', '0.1.0', 'v0.1.0\nanything=bad', 'v0.1.0;echo bad'])
def test_mismatched_or_injected_tags_rejected(project, tag):
    with pytest.raises(ValueError, match='Tag must match'):
        validate(project, tag)


@pytest.mark.parametrize('version', ['01.0.0', '0.1', '0.1.0-dev', '1.0.0rc01', '1.0.0+local'])
def test_noncanonical_versions_rejected(project, version):
    project.write_text(project.read_text().replace('0.1.0', version))
    with pytest.raises(ValueError, match='canonical'):
        validate(project)


@pytest.mark.parametrize('name', ['/absolute', '../outside', 'core/../../outside', 'core\\outside',
                                'core/.env', '.ghost/ghost.db', '.venv/lib.py', 'core/__pycache__/x.pyc'])
def test_unsafe_and_runtime_paths_rejected(name):
    with pytest.raises(ValueError):
        safe_member(name)


def artifacts(project, *, extra_wheel=None, extra_tar=None, metadata_version='0.1.0', license_text=None):
    dist = project.parent / 'dist'
    dist.mkdir()
    stem = 'ghost_debugger-0.1.0'
    metadata = f'Name: ghost-debugger\nVersion: {metadata_version}\nLicense-Expression: MIT\nRequires-Python: >=3.12\n'.encode()
    license_data = license_text if license_text is not None else (project.parent / 'LICENSE').read_bytes()
    members = {stem + '.dist-info/METADATA': metadata,
               stem + '.dist-info/licenses/LICENSE': license_data,
               stem + '.dist-info/entry_points.txt': b'[console_scripts]\nghost = surfaces.entrypoint:main\n',
               'config/security_rules.yaml': b'rules: []\n', 'surfaces/entrypoint.py': b'# test fixture\n'}
    if extra_wheel:
        members.update(extra_wheel)
    with zipfile.ZipFile(dist / (stem + '-py3-none-any.whl'), 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    members = {stem + '/PKG-INFO': metadata, stem + '/LICENSE': license_data,
               stem + '/pyproject.toml': project.read_bytes()}
    if extra_tar:
        members.update(extra_tar)
    with tarfile.open(dist / (stem + '.tar.gz'), 'w:gz') as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return dist


def test_valid_artifacts_have_exact_checksums_and_reviewable_notes(project):
    dist = artifacts(project)
    result = prepare(project, dist)
    assert result['tag'] == 'v0.1.0'
    for line in (dist / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ')
        assert digest == hashlib.sha256((dist / name).read_bytes()).hexdigest()
    notes = (dist / 'release-notes.md').read_text()
    assert '0.1.0' in notes and 'not a production security certification' in notes
    assert 'dependencies retain their own licenses' in notes


@pytest.mark.parametrize('scenario', ['version', 'license', 'vendored', 'private-wheel', 'private-source',
                                    'wrong-root', 'stale-artifact', 'symlink', 'missing-rules'])
def test_bad_distributions_cannot_generate_assets(project, scenario):
    options = {}
    if scenario == 'version':
        options['metadata_version'] = '0.2.0'
    elif scenario == 'license':
        options['license_text'] = b'wrong license'
    elif scenario in {'vendored', 'private-wheel'}:
        options['extra_wheel'] = {'bandit/vendor.py' if scenario == 'vendored' else 'core/.env': b'private fixture'}
    elif scenario in {'private-source', 'wrong-root'}:
        options['extra_tar'] = {'ghost_debugger-0.1.0/.ghost/ghost.db' if scenario == 'private-source' else 'other/file': b'fixture'}
    dist = artifacts(project, **options)
    if scenario == 'stale-artifact':
        (dist / 'old.whl').write_bytes(b'old')
    elif scenario == 'symlink':
        wheel = next(dist.glob('*.whl'))
        moved = project.parent / 'wheel'
        wheel.rename(moved)
        wheel.symlink_to(moved)
    elif scenario == 'missing-rules':
        wheel = next(dist.glob('*.whl'))
        with zipfile.ZipFile(wheel) as archive:
            items = {name: archive.read(name) for name in archive.namelist() if name != 'config/security_rules.yaml'}
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name, data in items.items():
                archive.writestr(name, data)
    with pytest.raises((ValueError, KeyError)):
        prepare(project, dist)
    assert not (dist / 'SHA256SUMS').exists() and not (dist / 'release-notes.md').exists()
