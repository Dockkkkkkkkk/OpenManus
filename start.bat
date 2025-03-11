@echo off
echo 正在启动OpenManus集成应用...

REM 启动FastAPI应用，它将同时提供前端和API服务
python main.py

echo 如果应用自动关闭，请查看错误信息。 