#!/usr/bin/env bash
# Independently authored installer; uses the user's existing package manager.
set -euo pipefail

fail() { printf 'Ghost installation: %s\n' "$*" >&2; exit 1; }

if [[ $# -gt 0 ]]; then
    if [[ $# -eq 1 && $1 == --help ]]; then
        printf '%s\n' 'Install Ghost with Homebrew or uv on macOS/Linux.' \
            'Usage: bash install.sh' \
            'Homebrew installs Git, Python, uv and Linux Bubblewrap as dependencies.' \
            'Without Homebrew, install uv, Git and your OS sandbox first.'
        exit 0
    fi
    fail 'Usage: bash install.sh [--help]'
fi

platform=$(uname -s)
case "$platform" in
    Darwin|Linux) ;;
    *) fail 'Ghost currently supports macOS and Linux. On Windows, use a Linux environment such as WSL2.' ;;
esac

if command -v brew >/dev/null 2>&1; then
    brew tap devesh36/ghost https://github.com/Devesh36/ghost.git
    brew install --HEAD devesh36/ghost/ghost
elif command -v uv >/dev/null 2>&1; then
    command -v git >/dev/null 2>&1 || fail 'Git is required. Install it with your OS package manager, then rerun.'
    if [[ $platform == Linux ]]; then
        command -v bwrap >/dev/null 2>&1 || fail 'Install Bubblewrap first (Ubuntu/Debian: sudo apt install bubblewrap), then rerun.'
    else
        command -v sandbox-exec >/dev/null 2>&1 || fail 'macOS sandbox-exec is required for security checks.'
    fi
    uv tool install --python 3.12 'git+https://github.com/Devesh36/ghost.git'
    uv tool update-shell
    tool_bin=$(uv tool dir --bin)
    if ! command -v ghost >/dev/null 2>&1; then
        printf 'Open a new terminal, or run: "%s/ghost"\n' "$tool_bin"
    fi
else
    fail 'Install Homebrew (https://brew.sh) or uv (https://docs.astral.sh/uv/getting-started/installation/), then rerun this command.'
fi

printf '\n%s\n' 'Ghost installed. Inside your Git project, run:' \
    '  ghost doctor' '  ghost find' '  ghost brief' \
    'Add .ghost/ to that project’s .gitignore to keep local review data out of Git.'
