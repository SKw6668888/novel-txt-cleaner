@echo off
chcp 65001 >nul
echo ========================================
echo   网文清洗器 - 打包为单文件 exe
echo ========================================
echo.

REM 检查是否在虚拟环境中
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 并加入 PATH
    pause
    exit /b 1
)

echo [1/2] 安装依赖（Gradio 较大，首次约 1-2 分钟）...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo [2/2] 开始打包（分析+打包约 2-5 分钟，请耐心等待）...
pyinstaller cleaner.spec --noconfirm --log-level INFO
if %errorlevel% neq 0 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo   打包完成！
echo   可执行文件: dist\网文清洗器.exe
echo   双击即可运行，无需安装 Python
echo ========================================
pause
