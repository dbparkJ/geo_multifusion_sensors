#!/usr/bin/env sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT="$REPOSITORY_ROOT/safe_gard_test/code"
VIRTUALENV="$REPOSITORY_ROOT/.venv"

if [ ! -f "$PROJECT_ROOT/setup_env.py" ]; then
    echo "Installer not found: $PROJECT_ROOT/setup_env.py" >&2
    exit 1
fi
if [ -L "$VIRTUALENV" ]; then
    echo "Refusing symbolic-link virtualenv: $VIRTUALENV" >&2
    exit 1
fi

cd "$PROJECT_ROOT"
# Keep --venv last so this folder-contract installer always creates the real
# virtualenv expected at <pipeline>/.venv.
exec "$PROJECT_ROOT/scripts/setup_env.sh" \
    --config "$PROJECT_ROOT/configs/setup.yaml" "$@" --venv "$VIRTUALENV"
