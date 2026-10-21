#!/usr/bin/env bash
set -e

PYTHON_VERSION="3.14"

# Always include uv and tool bin directories in PATH for this session
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# 1. Check if uv is installed, download if missing
if ! command -v uv &> /dev/null; then
    echo "[INFO] uv not found. Downloading and installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    if ! command -v uv &> /dev/null; then
        echo "[ERROR] Failed to install or locate uv. Please restart your terminal."
        exit 1
    fi
fi

# 2. Install or update ruleflow (enforces Python version and overwrites stale shims)
echo "[INFO] Installing / checking for updates to ruleflow (Python $PYTHON_VERSION)..."
if ! uv tool install --python "$PYTHON_VERSION" --upgrade --force --refresh ruleflow; then
    if ! command -v studio &> /dev/null; then
        echo "[ERROR] Failed to install ruleflow."
        exit 1
    fi
    echo "[WARNING] Update check failed (offline?). Proceeding with existing version..."
fi

# 3. Run RuleFlow Studio directly from the installed tool environment
echo "[INFO] Launching RuleFlow Studio..."
studio
