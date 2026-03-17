@echo off
chcp 65001 >nul
echo ========================================
echo   NovelCleaner - Build to single exe
echo ========================================
echo.

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python and add to PATH.
    pause
    exit /b 1
)

REM Use venv (create if not exists)
if not exist "venv" (
    echo [1/4] Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv
        pause
        exit /b 1
    )
)

echo [1/4] Activating venv...
call venv\Scripts\activate.bat

echo [2/4] Installing dependencies (Gradio is large, first run ~1-2 min)...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Dependency install failed
    pause
    exit /b 1
)

echo [3/4] Cleaning old build artifacts...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

echo [4/4] Building (analysis+build ~2-5 min, please wait)...
pyinstaller cleaner.spec --noconfirm --log-level INFO
if %errorlevel% neq 0 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Build complete!
echo   Executable: dist\NovelCleaner.exe
echo   Double-click to run, no Python needed
echo ========================================
pause
