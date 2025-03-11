from fastapi import FastAPI, Body, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Annotated
import json
import queue
import time
import asyncio
import os
from pathlib import Path
from starlette.responses import Response, FileResponse

app = FastAPI()

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建消息队列
message_queue = queue.Queue()

# 日志拦截器函数，用于捕获控制台输出
def log_interceptor(message):
    """将日志消息添加到队列中"""
    message_queue.put(message)

async def event_generator():
    """生成SSE事件流"""
    # 发送连接确认消息
    yield "event: connect\ndata: {\"status\":\"connected\"}\n\n"
    
    try:
        while True:
            if not message_queue.empty():
                message = message_queue.get()
                # 将消息格式化为SSE格式
                yield f"event: log\ndata: {json.dumps({'content': message})}\n\n"
            else:
                # 保持连接活跃
                yield ":\n\n"
                await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        print("SSE连接已关闭")

# 前端静态文件目录路径
frontend_dir = Path(__file__).parent.parent / "frontend"
index_html_path = frontend_dir / "index.html"

# 如果前端构建目录存在，则挂载静态文件
if (frontend_dir / "dist").exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir / "dist" / "assets")), name="static")
else:
    # 如果没有构建目录，则直接挂载src目录
    app.mount("/src", StaticFiles(directory=str(frontend_dir / "src")), name="src")
    app.mount("/node_modules", StaticFiles(directory=str(frontend_dir / "node_modules")), name="node_modules")

# 确保至少有一个index.html
if not index_html_path.exists():
    # 创建一个简单的index.html
    with open(index_html_path, "w", encoding="utf-8") as f:
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
        }
        .app-container {
            display: flex;
            flex: 1;
        }
        .input-panel {
            width: 30%;
            padding: 20px;
            border-right: 1px solid #eee;
        }
        .log-panel {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }
        textarea {
            width: 100%;
            min-height: 100px;
            padding: 10px;
            margin-bottom: 10px;
        }
        button {
            padding: 10px 20px;
            background: #2c3e50;
            color: white;
            border: none;
            cursor: pointer;
        }
        #logs {
            white-space: pre-wrap;
            font-family: monospace;
            background: #f5f5f5;
            padding: 10px;
            border-radius: 5px;
            min-height: 300px;
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
            logs.innerHTML += '已连接到OpenManus系统\\n';
        });
        
        eventSource.addEventListener('log', (event) => {
            const data = JSON.parse(event.data);
            if (data.content) {
                logs.innerHTML += data.content + '\\n';
                logs.scrollTop = logs.scrollHeight;
            }
        });
        
        eventSource.onerror = () => {
            console.error('SSE连接错误');
            logs.innerHTML += '连接已断开，尝试重新连接...\\n';
        };
        
        // 发送命令
        const promptInput = document.getElementById('prompt');
        const sendButton = document.getElementById('send');
        
        sendButton.addEventListener('click', async () => {
            const content = promptInput.value.trim();
            if (!content) return;
            
            logs.innerHTML += `用户: ${content}\\n`;
            
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
                
                promptInput.value = '';
            } catch (error) {
                console.error('发送消息失败:', error);
                logs.innerHTML += `发送消息失败: ${error.message}\\n`;
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

@app.get("/api/logs")
async def stream_logs():
    """提供日志流端点"""
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream"
    }
    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers=headers
    )

@app.post("/api/prompt")
async def handle_prompt(prompt: Annotated[str, Body(embed=True)]):
    """处理用户输入的提示，替代控制台输入"""
    # TODO: 这里需要和OpenManus的输入处理逻辑集成
    # 例如，可以将prompt放入一个队列，由主程序处理
    print(f"收到提示: {prompt}")
    return {"status": "success", "message": "命令已提交"}

@app.get("/{full_path:path}")
async def serve_frontend(request: Request, full_path: str):
    """提供前端页面"""
    # 如果是API请求，让其他路由处理
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    
    # 返回index.html
    return FileResponse(index_html_path) 