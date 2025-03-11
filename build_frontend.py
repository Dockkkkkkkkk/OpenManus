#!/usr/bin/env python
import os
import shutil
import subprocess
from pathlib import Path
import sys

def build_frontend():
    """构建前端项目并将其集成到FastAPI应用中"""
    # 获取项目根目录
    root_dir = Path(__file__).parent
    # 前端目录
    frontend_dir = root_dir / "frontend"
    # 静态目录
    static_dir = root_dir / "static"
    # 前端构建输出目录
    frontend_static_dir = static_dir / "frontend"
    
    # 确保静态目录存在
    static_dir.mkdir(exist_ok=True)
    frontend_static_dir.mkdir(exist_ok=True)
    
    # 检查前端目录是否存在
    if not frontend_dir.exists():
        print(f"前端目录不存在！{frontend_dir}")
        create_fallback_frontend(frontend_static_dir)
        return True
        
    # 确认package.json存在
    package_json = frontend_dir / "package.json"
    if not package_json.exists():
        print(f"前端目录中找不到package.json文件！{package_json}")
        create_fallback_frontend(frontend_static_dir)
        return True
        
    print("正在构建前端项目...")
    
    try:
        # 进入前端目录
        cwd = os.getcwd()  # 保存当前目录
        os.chdir(frontend_dir)
        
        # 安装依赖
        print("安装依赖...")
        try:
            if os.name == 'nt':  # Windows
                subprocess.run(['npm.cmd', 'install'], check=True)
            else:  # Unix/Linux/Mac
                subprocess.run(['npm', 'install'], check=True)
        except subprocess.CalledProcessError as e:
            print(f"安装依赖失败！错误：{e}")
            os.chdir(cwd)  # 恢复原来的工作目录
            create_fallback_frontend(frontend_static_dir)
            return True
        
        # 构建前端项目
        print("构建前端项目...")
        try:
            if os.name == 'nt':  # Windows
                subprocess.run(['npm.cmd', 'run', 'build'], check=True)
            else:  # Unix/Linux/Mac
                subprocess.run(['npm', 'run', 'build'], check=True)
        except subprocess.CalledProcessError as e:
            print(f"构建前端项目失败！错误：{e}")
            os.chdir(cwd)  # 恢复原来的工作目录
            create_fallback_frontend(frontend_static_dir)
            return True
        
        # 复制构建输出到静态目录
        print("复制构建输出到静态目录...")
        build_dir = frontend_dir / "dist"
        
        if not build_dir.exists():
            print(f"构建输出目录不存在！{build_dir}")
            os.chdir(cwd)  # 恢复原来的工作目录
            create_fallback_frontend(frontend_static_dir)
            return True
        
        # 删除之前的构建输出
        for item in frontend_static_dir.glob("*"):
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        
        # 复制新的构建输出
        for item in build_dir.glob("*"):
            if item.is_file():
                shutil.copy2(item, frontend_static_dir)
            elif item.is_dir():
                dst_dir = frontend_static_dir / item.name
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(item, dst_dir)
        
        # 确认index.html存在
        if not (frontend_static_dir / "index.html").exists():
            # 如果没有找到index.html，可能是构建配置问题
            if (build_dir / "index.html").exists():
                shutil.copy2(build_dir / "index.html", frontend_static_dir / "index.html")
            else:
                create_fallback_frontend(frontend_static_dir)
        
        # 恢复原来的工作目录
        os.chdir(cwd)
        print("前端构建完成并集成到FastAPI应用中！")
        return True
    except Exception as e:
        print(f"构建过程中发生错误：{e}")
        try:
            # 恢复原来的工作目录
            os.chdir(cwd)
        except:
            pass
        create_fallback_frontend(frontend_static_dir)
        return True

def create_fallback_frontend(output_dir):
    """创建一个备用的前端页面"""
    print(f"创建备用前端页面...")
    try:
        # 确保输出目录存在
        output_dir.mkdir(exist_ok=True, parents=True)
        
        # 创建index.html
        index_path = output_dir / "index.html"
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenManus AI助手</title>
    <style>
        body { 
            font-family: sans-serif; 
            max-width: 1200px; 
            margin: 0 auto; 
            padding: 20px;
            display: flex;
            flex-direction: column;
            height: 100vh;
            background-color: #f7f7f7;
        }
        .app-container {
            display: flex;
            flex: 1;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            border-radius: 10px;
            overflow: hidden;
            background-color: white;
        }
        .input-panel {
            width: 30%;
            padding: 20px;
            border-right: 1px solid #eee;
            display: flex;
            flex-direction: column;
        }
        .log-panel {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            background-color: #f9f9f9;
        }
        h1, h2 {
            color: #333;
            margin-top: 0;
        }
        textarea {
            width: 100%;
            min-height: 100px;
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            resize: vertical;
            font-family: inherit;
            flex: 1;
        }
        button {
            padding: 10px 20px;
            background: #2c3e50;
            color: white;
            border: none;
            cursor: pointer;
            border-radius: 5px;
            transition: background 0.3s;
        }
        button:hover {
            background: #1a252f;
        }
        #logs {
            white-space: pre-wrap;
            font-family: monospace;
            background: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            min-height: 300px;
            max-height: 70vh;
            overflow-y: auto;
            border: 1px solid #ddd;
        }
        .message {
            margin-bottom: 10px;
            padding: 8px 12px;
            border-radius: 5px;
        }
        .user {
            background-color: #e6f7ff;
            border-left: 4px solid #1890ff;
            text-align: left;
        }
        .system {
            background-color: #f6ffed;
            border-left: 4px solid #52c41a;
            text-align: left;
        }
        .error {
            background-color: #fff2f0;
            border-left: 4px solid #ff4d4f;
        }
    </style>
</head>
<body>
    <h1>OpenManus AI助手</h1>
    <div class="app-container">
        <div class="input-panel">
            <h2>命令输入</h2>
            <textarea id="prompt" placeholder="输入您的指令..."></textarea>
            <button id="send">发送</button>
        </div>
        <div class="log-panel">
            <h2>系统日志</h2>
            <div id="logs"></div>
        </div>
    </div>
    
    <script>
        // 建立SSE连接
        const eventSource = new EventSource('/api/logs');
        const logs = document.getElementById('logs');
        
        eventSource.addEventListener('connect', (event) => {
            console.log('连接已建立');
            addMessage('已连接到OpenManus系统', 'system');
        });
        
        eventSource.addEventListener('log', (event) => {
            const data = JSON.parse(event.data);
            if (data.content) {
                // 检查是否是用户消息
                if (data.content.startsWith('用户:')) {
                    const userMessage = data.content.substring(3).trim();
                    addMessage(userMessage, 'user');
                } else {
                    addMessage(data.content, 'system');
                }
            }
        });
        
        eventSource.onerror = () => {
            console.error('SSE连接错误');
            addMessage('连接已断开，尝试重新连接...', 'error');
        };
        
        function addMessage(content, type) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${type}`;
            messageDiv.textContent = content;
            logs.appendChild(messageDiv);
            logs.scrollTop = logs.scrollHeight;
        }
        
        // 发送命令
        const promptInput = document.getElementById('prompt');
        const sendButton = document.getElementById('send');
        
        sendButton.addEventListener('click', async () => {
            const content = promptInput.value.trim();
            if (!content) return;
            
            try {
                const response = await fetch('/api/prompt', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ prompt: content })
                });
                
                if (!response.ok) {
                    throw new Error('请求失败');
                }
                
                // 清空输入框
                promptInput.value = '';
            } catch (error) {
                console.error('发送消息失败:', error);
                addMessage(`发送消息失败: ${error.message}`, 'error');
            }
        });
        
        // 自动获取历史记录
        async function fetchHistory() {
            try {
                const response = await fetch('/api/history');
                if (response.ok) {
                    const data = await response.json();
                    if (data.history && data.history.length > 0) {
                        // 只显示最近10条
                        const recentHistory = data.history.slice(-10);
                        for (const msg of recentHistory) {
                            const type = msg.role === 'user' ? 'user' : 'system';
                            addMessage(msg.content, type);
                        }
                    }
                }
            } catch (error) {
                console.error('获取历史记录失败:', error);
            }
        }
        
        // 按Enter发送消息
        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendButton.click();
            }
        });
        
        // 页面加载后获取历史记录
        // window.addEventListener('load', fetchHistory);
    </script>
</body>
</html>""")
        print(f"已创建备用前端页面：{index_path}")
        return True
    except Exception as e:
        print(f"创建备用页面时发生错误：{e}")
        return False

if __name__ == "__main__":
    # 执行构建
    success = build_frontend()
    sys.exit(0)  # 始终返回成功，因为我们已经创建了备用页面 