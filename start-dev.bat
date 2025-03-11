@echo off
echo 正在启动OpenManus开发环境...

REM 使用uvicorn以开发模式启动应用，支持代码热重载
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

echo 如果应用自动关闭，请查看错误信息。

REM 先确保后端API服务启动
start cmd /k python main.py

REM 等待几秒确保API服务完全启动
timeout /t 5

REM 启动前端开发服务器
cd frontend
start cmd /k npm run start

echo OpenManus开发环境已启动！
echo 前端界面: http://localhost:3000
echo 后端API: http://localhost:8000
echo 请确保没有防火墙或安全软件阻止这些端口
echo.
echo 提示：如果无法加载界面，请检查前端构建是否成功，或者尝试在frontend目录运行 npm run build 