"""Explicit, non-deleting recovery of recorded security workspaces."""
import hashlib
import os
from pathlib import Path
import re

from infrastructure.database.inspection import checked_file, inspection_folder, readonly_history
from infrastructure.database.migrations import check_schema, check_version
from infrastructure.database.recovery_lock import recovery_guard
from infrastructure.database.repair_inspection import repair_records
from infrastructure.database.repository import Database
from infrastructure.repository.git import git, GitError
from infrastructure.safety.sandbox.inventory import registered_paths


def _paths(repo, run):
    if re.fullmatch(r'[0-9a-f]{32}', run['id']) is None:
        raise ValueError('Invalid recovery identity')
    name = 'repair-' + run['id']
    return repo / '.ghost/worktrees' / name, repo / '.ghost/recovered' / name


def _present(repo, path):
    """Inspect only a direct child of an owned no-follow storage directory."""
    with inspection_folder(repo) as handles:
        if handles is None:
            return False
        stack, folder = handles
        try:
            parent = os.open(path.parent.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
        except FileNotFoundError:
            return False
        stack.callback(os.close, parent)
        if os.fstat(parent).st_uid != os.geteuid():
            raise ValueError('Storage directory is not owned by this user')
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return True


def _owned_workspace(repo, path, run):
    with inspection_folder(repo) as handles:
        if handles is None:
            raise ValueError('Recovery storage is missing')
        stack, folder = handles
        parent = os.open(path.parent.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
        stack.callback(os.close, parent)
        child = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        stack.callback(os.close, child)
        info = os.fstat(child)
        attached = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (os.fstat(parent).st_uid != os.geteuid() or info.st_uid != os.geteuid()
                or [info.st_dev, info.st_ino] != list(run['workspace_identity'] or [])
                or (attached.st_dev, attached.st_ino) != (info.st_dev, info.st_ino)):
            raise ValueError('Workspace identity differs')
        checked_file(stack, child, '.git')
        fd = os.open('.git', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=child)
        stack.callback(os.close, fd)
        if hashlib.sha256(os.read(fd, 8193)).hexdigest() != run['gitfile_sha256']:
            raise ValueError('Workspace Git identity differs')
        registration = next((item for item in registered_paths(repo) if item['path'] == str(path)), None)
        if not registration or registration['locked'] or registration['prunable']:
            raise ValueError('Workspace is missing, locked or prunable')
        if (git(path, 'rev-parse', '--show-toplevel').strip() != str(path)
                or git(path, 'rev-parse', '--abbrev-ref', 'HEAD').strip() != 'HEAD'
                or git(path, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip()
                != git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip()):
            raise ValueError('Workspace registration differs')


def archive_candidate(repo, run):
    if run['stage'] not in {'prepared', 'cleanup_pending'}:
        return False
    try:
        source, destination = _paths(repo, run)
        # Never interpret a dangling link as an absent destination or source.
        source_present, destination_present = _present(repo, source), _present(repo, destination)
        if source_present and not destination_present:
            _owned_workspace(repo, source, run)
        elif not source_present and destination_present:
            # A previous move may have completed before the record was saved.
            _owned_workspace(repo, destination, run)
        else:
            return False
        return True
    except (OSError, ValueError, GitError):
        return False


def archive_repair(repo: Path, run_id: str):
    """Move to retained storage under the existing lock; never delete or verify."""
    repo = repo.resolve(strict=True)
    if re.fullmatch(r'[0-9a-f]{32}', run_id) is None:
        raise ValueError('Use an exact repair workspace ID from ghost recover.')
    with recovery_guard(repo) as lock:
        if lock != 'available':
            raise ValueError('Recovery requires an existing available checkout lock. Stop Ghost and inspect the plan.')
        with readonly_history(repo) as connection:
            if connection is None:
                raise ValueError('No repair history is available')
            version = check_version(connection)
            check_schema(connection, version=version)
            matches = [(solution, run) for solution in repair_records(connection)
                       for run in solution.recovery_runs if run.id == run_id]
        if len(matches) != 1:
            raise ValueError('No unique recorded repair workspace matches this ID.')
        solution, run = matches[0]
        metadata = run.model_dump(mode='json')
        if not archive_candidate(repo, metadata):
            raise ValueError('Workspace is not eligible for archiving. Retain it and inspect ghost recover; '
                             'interrupted execution, uncertain ownership and locked paths are never moved.')
        source, destination = _paths(repo, metadata)
        # Open persistence before changing the filesystem, retaining all normal
        # storage checks. A move/save crash is recoverable by the same command.
        db = Database(repo)
        with inspection_folder(repo) as handles:
            stack, folder = handles
            try:
                os.mkdir('recovered', 0o700, dir_fd=folder)
            except FileExistsError:
                pass
            archive = os.open('recovered', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
            stack.callback(os.close, archive)
            if os.fstat(archive).st_uid != os.geteuid():
                raise ValueError('Archive storage is not owned by this user')
            if _present(repo, source):
                if _present(repo, destination):
                    raise ValueError('Archive destination exists; nothing was overwritten')
                _owned_workspace(repo, source, metadata)
                git(repo, 'worktree', 'move', str(source), str(destination), timeout=30)
            _owned_workspace(repo, destination, metadata)
            run.stage = 'archived'
            db.save_solution(solution)
        return {'id': run.id, 'archive': str(destination.relative_to(repo)),
                'deleted': False, 'verification_changed': False,
                'next_step': 'Files retained. Run a fresh solve and any required Challenge before applying.'}
