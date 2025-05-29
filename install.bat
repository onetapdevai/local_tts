@echo off
setlocal enabledelayedexpansion

:: --- CONFIG ---
set VENV_DIR=.local_tts_venv
set REQUIREMENTS_INPUT_FILE=requirements.in
set REQUIREMENTS_LOCK_FILE=requirements.lock.txt

if not defined UV_APP_DRY set "UV_APP_DRY=0"
echo Dry Run Mode: %UV_APP_DRY%

:: --- Core Setup ---
where python >nul || (echo ERROR: Python missing! && pause && exit /b 1)
where uv >nul || (echo ERROR: UV missing! && pause && exit /b 1)

if not exist "%VENV_DIR%" (
    echo Creating venv...
    uv venv "%VENV_DIR%" --python python3.11 || (
        echo ERROR: Venv creation failed!
        pause
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate"

echo Ensuring lock file is up to date...
uv pip compile "%REQUIREMENTS_INPUT_FILE%" -o "%REQUIREMENTS_LOCK_FILE%" || (
    echo ERROR: Lock file generation failed!
    pause
    exit /b 1
)

:: Install from lock file
echo Installing dependencies from lock file...
uv pip sync "%REQUIREMENTS_LOCK_FILE%" || (
    echo ERROR: Dependency installation from lock file failed!
    pause
    exit /b 1
)

:: Conditional PyTorch install
if "%UV_APP_DRY%"=="0" (
    echo Installing PyTorch...
    python install_torch.py || (
        echo WARNING: PyTorch install failed. App may lack GPU support.
    )
) else (
    echo [Dry Run] Skipped PyTorch installation
)
echo Starting new command prompt with venv activated...
cmd /k "%VENV_DIR%\Scripts\activate.bat"