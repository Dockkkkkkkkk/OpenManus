@echo off
echo ===================================
echo 启动OpenManus AI助手 (前后端不分离版)
echo ===================================

REM 确保存在Python环境
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Python未安装或未添加到PATH环境变量中！
    echo 请安装Python 3.8+并确保添加到PATH环境变量中。
    pause
    exit /b 1
)

REM 检查requirements.txt是否存在
if not exist requirements.txt (
    echo requirements.txt文件不存在！
    pause
    exit /b 1
)

REM 安装依赖
echo 正在检查依赖...
python -m pip install -r requirements.txt

REM 执行前端构建
echo 正在构建前端...
python build_frontend.py

REM 启动应用
echo 正在启动OpenManus AI助手...
python main.py

pause 