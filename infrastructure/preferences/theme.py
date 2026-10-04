"""Bounded, atomic, credential-free theme preferences with link protection."""
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from config.theme import THEMES


class PreferenceError(ValueError):
    pass


def directory() -> Path:
    base = Path(os.getenv('XDG_CONFIG_HOME') or Path.home() / '.config')
    if not base.is_absolute():
        raise PreferenceError('XDG_CONFIG_HOME must be an absolute directory.')
    return base / 'ghost'


def read_saved() -> str | None:
    try:
        folder = os.open(directory(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError:
        raise PreferenceError('Could not safely read Ghost theme preferences.') from None
    try:
        try:
            fd = os.open('theme.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1024:
                raise ValueError
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                data = json.loads(stream.read(1025))
            if not isinstance(data, dict) or set(data) != {'theme'} or data['theme'] not in THEMES:
                raise ValueError
            return data['theme']
        finally:
            os.close(fd)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise PreferenceError('Invalid theme preferences. Run ghost theme <name> to reset them.') from None
    finally:
        os.close(folder)


def save(name: str) -> None:
    if name not in THEMES:
        raise PreferenceError('Unknown theme. Use ghost theme to list available themes.')
    folder = None
    temporary = '.theme-' + uuid4().hex + '.tmp'
    try:
        directory().mkdir(parents=True, mode=0o700, exist_ok=True)
        folder = os.open(directory(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.stat('theme.json', dir_fd=folder, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise PreferenceError('Theme preferences must be a regular file without links.')
        except FileNotFoundError:
            pass
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'theme': name}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, 'theme.json', src_dir_fd=folder, dst_dir_fd=folder)
    except OSError:
        raise PreferenceError('Could not safely save the theme. Check Ghost configuration directory access.') from None
    finally:
        if folder is not None:
            try:
                os.unlink(temporary, dir_fd=folder)
            except FileNotFoundError:
                pass
            os.close(folder)


def startup() -> tuple[str, str | None]:
    override = os.getenv('GHOST_THEME')
    if override:
        if override in THEMES:
            return override, None
        return 'ghost', 'Unknown GHOST_THEME; using ghost. Run ghost theme for available names.'
    try:
        return read_saved() or 'ghost', None
    except PreferenceError as exc:
        return 'ghost', str(exc)
