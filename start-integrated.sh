#!/bin/bash

echo "==================================="
echo "启动OpenManus AI助手 (前后端不分离版)"
echo "==================================="

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "Python未安装！"
    echo "请安装Python 3.8+。"
    exit 1
fi

# 检查requirements.txt是否存在
if [ ! -f requirements.txt ]; then
    echo "requirements.txt文件不存在！"
    exit 1
fi

# 安装依赖
echo "正在检查依赖..."
python3 -m pip install -r requirements.txt

# 执行前端构建
echo "正在构建前端..."
python3 build_frontend.py

# 启动应用
echo "正在启动OpenManus AI助手..."
python3 main.py 