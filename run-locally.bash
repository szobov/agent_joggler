#!/usr/bin/env bash

# shellcheck disable=SC3040
set -euxo pipefail

VENV_DIR=".venv2"

function check_venv_exists() {
    if [ -d "$VENV_DIR" ]; then
        return 0
    else
        return 1
    fi
}

function activate_and_sync() {
    echo "Activating virtual environment and syncing dependencies..."
    # shellcheck disable=SC1090
    source "${VENV_DIR}/bin/activate"
    uv sync
    deactivate
}

function create_venv() {
    echo "Creating virtual environment..."
    python -m pip install --upgrade pip
    python -m pip install uv
    python -m uv python install 3.12
    python -m uv venv --python 3.12 "${VENV_DIR}"
}

function main() {
    local current_dir
    current_dir="$(dirname "$0")"
    cd "${current_dir}" || exit 1

    if check_venv_exists; then
        echo "Virtual environment exists."
        activate_and_sync
    else
        echo "Virtual environment does not exist."
        create_venv
        activate_and_sync
    fi

    echo "Running application..."
    # shellcheck disable=SC1090
    .venv/bin/python run.py
}

main
