@echo off
setlocal enabledelayedexpansion

set "PYTHON_VERSION=3.14"

:: Always ensure the uv / tool bin folder is on PATH for this session
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

:: 1. Check if uv is installed, download if missing
where uv >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] uv not found. Downloading and installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

    where uv >nul 2>nul
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to install or locate uv. Please restart your terminal.
        pause
        exit /b 1
    )
)

:: 2. Install or update ruleflow (enforces Python version and overwrites stale shims)
echo [INFO] Installing / checking for updates to ruleflow ^(Python %PYTHON_VERSION%^)...
uv tool install --python %PYTHON_VERSION% --upgrade --force --refresh ruleflow
if %ERRORLEVEL% neq 0 (
    where studio >nul 2>nul
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to install ruleflow.
        pause
        exit /b 1
    )
    echo [WARNING] Update check failed ^(offline?^). Proceeding with existing version...
)

:: 3. Run RuleFlow Studio directly from the installed tool environment
echo [INFO] Launching RuleFlow Studio...
studio

pause
