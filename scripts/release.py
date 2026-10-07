"""Independent, standard-library release checks; does not publish or create tags."""
import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:(a|b|rc)(0|[1-9][0-9]*))?')
PACKAGES = {'bootstrap', 'config', 'core', 'infrastructure', 'surfaces'}


def validate(project: Path, tag: str | None = None) -> dict:
    data = tomllib.loads(project.read_text())['project']
    version = data['version']
    match = VERSION.fullmatch(version) if isinstance(version, str) else None
    if not match or data['name'] != 'ghost-debugger' or data['license'] != 'MIT':
        raise ValueError('Expected ghost-debugger, MIT, and a canonical X.Y.Z or X.Y.ZrcN/aN/bN version.')
    expected = 'v' + version
    if tag is not None and tag != expected:
        raise ValueError(f'Tag must match pyproject.toml exactly: {expected}')
    return {'version': version, 'tag': expected, 'prerelease': bool(match.group(4))}


def safe_member(name: str) -> tuple[str, ...]:
    parts = PurePosixPath(name).parts
    if not parts or name.startswith('/') or '\\' in name or '..' in parts or any(
            part in {'.git', '.ghost', '.venv', '__pycache__', '.pytest_cache'}
            or (part.startswith('.env') and part != '.env.example') for part in parts):
        raise ValueError('Unsafe or private distribution member: ' + name)
    return parts


def verify_metadata(content: bytes, version: str) -> None:
    headers = BytesParser().parsebytes(content)
    expected = {'Name': 'ghost-debugger', 'Version': version, 'License-Expression': 'MIT',
                'Requires-Python': '>=3.12'}
    if any(headers.get(key) != value for key, value in expected.items()):
        raise ValueError('Distribution metadata does not match the release project.')


def checksum(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(project: Path, dist: Path) -> dict:
    result = validate(project)
    version = result['version']
    stem = 'ghost_debugger-' + version
    wheel, source = dist / (stem + '-py3-none-any.whl'), dist / (stem + '.tar.gz')
    if set(p.name for p in dist.iterdir()) != {wheel.name, source.name}:
        raise ValueError('Release directory must contain exactly the expected wheel and source archive.')
    if wheel.is_symlink() or source.is_symlink():
        raise ValueError('Distribution files must not be symlinks.')
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate wheel members.')
        for name in names:
            parts = safe_member(name)
            if parts[0] not in PACKAGES | {stem + '.dist-info'}:
                raise ValueError('Unexpected wheel package: ' + name)
            if stat.S_ISLNK(archive.getinfo(name).external_attr >> 16):
                raise ValueError('Wheel member is a symlink.')
        verify_metadata(archive.read(stem + '.dist-info/METADATA'), version)
        if archive.read(stem + '.dist-info/licenses/LICENSE') != (project.parent / 'LICENSE').read_bytes():
            raise ValueError('Wheel license differs from the project license.')
        archive.getinfo('config/security_rules.yaml')
        entry = archive.read(stem + '.dist-info/entry_points.txt').decode()
        if 'ghost = surfaces.entrypoint:main' not in entry:
            raise ValueError('Ghost CLI entrypoint missing from wheel.')
    with tarfile.open(source, 'r:gz') as archive:
        names = archive.getnames()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate source archive members.')
        for member in archive.getmembers():
            parts = safe_member(member.name)
            if parts[0] != stem or not (member.isfile() or member.isdir()):
                raise ValueError('Unexpected source archive root or special member.')
        verify_metadata(archive.extractfile(stem + '/PKG-INFO').read(), version)
        if archive.extractfile(stem + '/LICENSE').read() != (project.parent / 'LICENSE').read_bytes():
            raise ValueError('Source archive license differs from the project license.')
        if archive.extractfile(stem + '/pyproject.toml').read() != project.read_bytes():
            raise ValueError('Source archive project configuration differs from the checkout.')
    checksums = ''.join(f'{checksum(path)}  {path.name}\n'
                        for path in (wheel, source))
    (dist / 'SHA256SUMS').write_text(checksums)
    (dist / 'release-notes.md').write_text(
        f'# Ghost {version}\n\nLocal-first Python and JavaScript/TypeScript security review.\n\n'
        'Install the wheel with Python 3.12+: `python -m pip install ghost_debugger-'
        + version + '-py3-none-any.whl`. Git and OS confinement are required for experiments: '
        'sandbox-exec on macOS, bubblewrap on Linux. Run `ghost --help` and `ghost demo --security`.\n\n'
        'The release pipeline gates this draft on Linux/macOS tests and a clean wheel-install security demo. '
        'Review the workflow results and docs/launch-readiness.md before publishing. '
        'Passing CI is not a production security certification.\n\n'
        'Ghost source is MIT licensed; separately installed dependencies retain their own licenses. '
        'See docs/source-provenance.md. SHA256SUMS covers both distributions; checksums are not signatures.\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['validate', 'prepare'])
    parser.add_argument('--tag')
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    try:
        result = validate(ROOT / 'pyproject.toml', args.tag)
        if args.action == 'prepare':
            result = prepare(ROOT / 'pyproject.toml', args.dist)
    except (ValueError, KeyError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'Release validation failed: {exc}\n')
    if args.github_output:
        with args.github_output.open('a') as output:
            for key, value in result.items():
                output.write(f'{key}={str(value).lower() if isinstance(value, bool) else value}\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
