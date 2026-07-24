@echo off
rem ============================================================
rem ZDQuote · Windows 一键打包（双击运行即可）
rem 前置：已安装 Python 3.10+ 并勾选 "Add Python to PATH"
rem ============================================================
cd /d "%~dp0"

WHERE python >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo [错误] 未检测到 Python。请先安装 Python 3.10+ 并勾选 "Add Python to PATH"。
    pause
    exit /b 1
)

echo >>> 安装依赖（若已装会自动跳过）
python -m pip install -U pip
python -m pip install -r requirements.txt

echo.
echo >>> 开始打包（PyInstaller，约 1~3 分钟）
python build_win.py

echo.
echo ============================================================
echo 构建完成：dist\ZDQuote\ZDQuote.exe
echo 如需生成安装包(ZDQuote_Setup.exe)，请用 Inno Setup 打开 installer_win.iss 编译。
echo ============================================================
pause
