#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEFAULT_REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=${ARCADE_REPO_ROOT:-$DEFAULT_REPO_ROOT}

if [ ! -d "$REPO_ROOT" ]; then
    echo "ARCADE_REPO_ROOT does not exist: $REPO_ROOT" >&2
    exit 1
fi

if [ ! -f "$REPO_ROOT/supervisor.py" ]; then
    echo "supervisor.py not found under $REPO_ROOT" >&2
    exit 1
fi

PYTHON_EXE=${ARCADE_PYTHON:-}
if [ -z "$PYTHON_EXE" ]; then
    if [ -x "$REPO_ROOT/.venv/bin/python3" ]; then
        PYTHON_EXE="$REPO_ROOT/.venv/bin/python3"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_EXE=$(command -v python3)
    else
        echo "python3 not found; set ARCADE_PYTHON to an absolute interpreter path" >&2
        exit 1
    fi
fi

if [ ! -x "$PYTHON_EXE" ]; then
    echo "Python interpreter is not executable: $PYTHON_EXE" >&2
    exit 1
fi

cd "$REPO_ROOT"
exec "$PYTHON_EXE" "$REPO_ROOT/supervisor.py"
