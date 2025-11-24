@echo off
chcp 65001 >nul
echo ======================================
echo    AI模型一键测评工具 v1.0
echo ======================================
echo.

echo [1/3] 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.7+
    pause
    exit /b 1
)
echo [成功] Python环境正常

echo.
echo [2/3] 检查依赖包...
pip show requests >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装依赖包...
    pip install -r requirements.txt
) else (
    echo [成功] 依赖包已安装
)

echo.
echo [3/3] 启动程序...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo [错误] 程序运行失败
    pause
)
