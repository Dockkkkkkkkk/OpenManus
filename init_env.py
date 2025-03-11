import os
import shutil
from pathlib import Path

def init_environment():
    """初始化项目环境，创建必要的目录结构"""
    # 获取当前目录
    root_dir = Path(__file__).parent
    
    # 创建static目录
    static_dir = root_dir / "static"
    static_dir.mkdir(exist_ok=True)
    
    # 创建frontend目录
    frontend_dir = static_dir / "frontend"
    frontend_dir.mkdir(exist_ok=True)
    
    # 创建基本的index.html文件
    index_path = frontend_dir / "index.html"
    if not index_path.exists():
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
        
        // 按Enter发送消息
        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendButton.click();
            }
        });
    </script>
</body>
</html>""")
    
    print(f"环境初始化完成！")
    print(f"已创建目录：{static_dir}")
    print(f"已创建目录：{frontend_dir}")
    print(f"已创建文件：{index_path}")

if __name__ == "__main__":
    init_environment() 