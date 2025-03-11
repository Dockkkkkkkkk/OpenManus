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
import uuid

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

# 用于存储对话历史的队列
conversation_history = []

# 获取项目根目录
ROOT_DIR = Path(__file__).parent.parent
# 定义静态文件目录
STATIC_DIR = ROOT_DIR / "static"
# 确保静态目录存在
STATIC_DIR.mkdir(exist_ok=True)
# 定义前端构建输出目录
FRONTEND_DIR = STATIC_DIR / "frontend"
# 定义index.html路径
INDEX_HTML_PATH = FRONTEND_DIR / "index.html"

# 日志拦截器函数，用于捕获控制台输出
def log_interceptor(message):
    """将日志消息添加到队列中"""
    try:
        print(f"日志拦截器接收到消息: {message}")
        
        # 处理日志消息，去除前缀
        processed_message = message
        if message and isinstance(message, str):
            # 检查是否包含常见的日志前缀模式
            if " | " in message:
                # 尝试去除时间戳和日志级别前缀，例如：2025-03-11 16:58:22.527 | INFO     | app.agent.toolcall:think:54 - 
                parts = message.split(" | ")
                if len(parts) >= 3 and " - " in parts[2]:
                    # 提取实际内容
                    content_parts = parts[2].split(" - ", 1)
                    if len(content_parts) > 1:
                        processed_message = content_parts[1].strip()
                # 处理简单的两部分格式：INFO | 内容
                elif len(parts) == 2:
                    processed_message = parts[1].strip()
            # 如果是INFO、WARNING等简单前缀，也去除
            elif any(message.startswith(prefix) for prefix in ["INFO | ", "WARNING | ", "ERROR | ", "INFO: ", "WARNING: ", "ERROR: "]):
                for prefix in ["INFO | ", "WARNING | ", "ERROR | ", "INFO: ", "WARNING: ", "ERROR: "]:
                    if message.startswith(prefix):
                        processed_message = message[len(prefix):].strip()
                        break
            
            # 处理带冒号的情况：INFO： 或 WARNING： 等
            elif "INFO：" in message or "WARNING：" in message or "ERROR：" in message:
                if "INFO：" in message:
                    processed_message = message.split("INFO：", 1)[1].strip()
                elif "WARNING：" in message:
                    processed_message = message.split("WARNING：", 1)[1].strip()
                elif "ERROR：" in message:
                    processed_message = message.split("ERROR：", 1)[1].strip()
        
        # 将处理后的消息放入队列
        message_queue.put(processed_message)
        
        # 保存到对话历史
        if processed_message and isinstance(processed_message, str):
            conversation_history.append({"role": "system", "content": processed_message})
            # 限制历史记录长度
            if len(conversation_history) > 100:
                conversation_history.pop(0)
    except Exception as e:
        print(f"日志拦截器错误: {e}")

async def event_generator():
    """生成SSE事件流"""
    # 发送连接确认消息
    yield "event: connect\ndata: {\"status\":\"connected\"}\n\n"
    
    try:
        # 发送一个欢迎消息
        welcome_msg = "OpenManus系统已启动，等待您的指令..."
        yield f"event: log\ndata: {json.dumps({'content': welcome_msg})}\n\n"
        
        # 记录已发送的消息ID，避免重复发送
        sent_message_ids = set()
        # 每个连接使用唯一的标识符
        connection_id = str(uuid.uuid4())
        
        # 添加连接时间戳，只处理比连接时间更新的消息
        connection_timestamp = time.time()
        
        while True:
            try:
                if not message_queue.empty():
                    message = message_queue.get()
                    
                    # 为每条消息生成唯一ID (内容+时间戳的哈希值)
                    if isinstance(message, str):
                        message_id = hash(message + str(time.time()))
                        
                        # 仅当消息未发送过且不是旧消息时才发送
                        if message_id not in sent_message_ids:
                            sent_message_ids.add(message_id)
                            
                            # 将消息格式化为SSE格式并发送
                            yield f"event: log\ndata: {json.dumps({'content': message})}\n\n"
                            
                            # 如果收到处理完成信号，清理集合以节省内存
                            if "处理完成" in message:
                                sent_message_ids.clear()
                                
                else:
                    # 保持连接活跃
                    await asyncio.sleep(0.1)
                    
                    # 定期清理长时间未使用的消息ID，避免内存泄漏
                    if len(sent_message_ids) > 1000:
                        sent_message_ids.clear()
                    
            except Exception as e:
                print(f"事件流错误: {str(e)}")
                await asyncio.sleep(0.1)
                
    except asyncio.CancelledError:
        # 正常关闭
        print("事件流已关闭")
        raise

# 如果前端构建目录存在，则挂载静态文件
frontend_dist = FRONTEND_DIR / "dist"
if frontend_dist.exists() and (frontend_dist / "assets").exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dist / "assets")), name="static")
elif FRONTEND_DIR.exists():
    # 如果没有构建目录，但存在前端目录，尝试挂载src目录
    frontend_src = FRONTEND_DIR / "src"
    frontend_node_modules = FRONTEND_DIR / "node_modules"
    
    if frontend_src.exists():
        app.mount("/src", StaticFiles(directory=str(frontend_src)), name="src")
    
    if frontend_node_modules.exists():
        app.mount("/node_modules", StaticFiles(directory=str(frontend_node_modules)), name="node_modules")

# 确保用于存放index.html的目录存在
FRONTEND_DIR.mkdir(exist_ok=True, parents=True)

# 确保至少有一个index.html
if not INDEX_HTML_PATH.exists():
    # 创建一个简单的index.html
    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
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
async def handle_prompt(prompt_data: dict):
    """处理用户输入的提示，替代控制台输入"""
    try:
        # 从JSON对象中提取prompt字段
        prompt = prompt_data.get("prompt", "")
        
        # 记录收到的请求
        print(f"收到提示: {prompt}")
        
        # 验证输入
        if not prompt or not isinstance(prompt, str) or len(prompt.strip()) == 0:
            error_msg = "请求内容不能为空"
            print(error_msg)
            return {"status": "error", "message": error_msg}
        
        # 保存到对话历史
        conversation_history.append({"role": "user", "content": prompt})
        
        # 发送到前端日志
        log_interceptor(f"用户: {prompt}")
        
        # 直接在这里处理用户输入，而不是通过队列
        try:
            # 导入Manus代理
            from app.agent.manus import Manus
            
            # 创建代理实例
            agent = Manus()
            
            # 记录处理开始
            warning_msg = f"正在处理您的请求: {prompt}"
            print(warning_msg)
            log_interceptor(warning_msg)
            
            # 异步执行代理
            asyncio.create_task(process_prompt_with_agent(agent, prompt))
            
            # 返回成功消息
            return {"status": "success", "message": "命令已提交"}
        except Exception as e:
            error_msg = f"创建代理失败: {str(e)}"
            print(error_msg)
            log_interceptor(error_msg)
            return {"status": "error", "message": error_msg}
    except Exception as e:
        # 记录错误
        error_msg = f"处理提示时出错: {str(e)}"
        print(error_msg)
        log_interceptor(error_msg)
        import traceback
        print(traceback.format_exc())
        
        # 返回错误信息
        return {"status": "error", "message": error_msg}

# 添加一个新函数，用于异步处理提示
async def process_prompt_with_agent(agent, prompt):
    """异步处理用户输入"""
    try:
        # 运行代理并获取结果
        result = await agent.run(prompt)
        
        # 处理结果 - 如果结果很长，按行分割发送
        print("处理完成，结果如下:")
        if isinstance(result, str) and result:
            lines = result.split('\n')
            for line in lines:
                if line.strip():  # 跳过空行
                    log_interceptor(line)
        else:
            log_interceptor(str(result))
        
        # 发送处理完成的消息
        log_interceptor("处理完成")
    except Exception as e:
        # 记录详细错误
        error_msg = f"执行失败: {str(e)}"
        print(error_msg)
        # 向前端发送简化的错误消息
        log_interceptor(f"执行错误: {str(e)}")
        log_interceptor("处理完成")

@app.get("/api/history")
async def get_history():
    """获取对话历史记录"""
    return {"history": conversation_history}

# 挂载静态文件目录
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 挂载前端静态资源
frontend_assets = FRONTEND_DIR / "assets"
if frontend_assets.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_assets)), name="assets")

@app.get("/{full_path:path}")
async def serve_frontend(request: Request, full_path: str):
    """提供前端页面"""
    # 如果是API请求，让其他路由处理
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    
    # 如果index.html存在，返回它
    if INDEX_HTML_PATH.exists():
        return FileResponse(INDEX_HTML_PATH)
    else:
        # 如果前端尚未构建，返回一个简单的HTML页面
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>OpenManus AI助手</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                h1 { color: #333; }
                .warning { color: #ff6600; }
                .container { border: 1px solid #ddd; padding: 20px; border-radius: 5px; }
                textarea { width: 100%; height: 100px; margin: 10px 0; }
                button { background: #4CAF50; color: white; padding: 10px 15px; border: none; cursor: pointer; }
                #output { background: #f5f5f5; padding: 10px; height: 300px; overflow-y: auto; margin-top: 20px; white-space: pre-wrap; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>OpenManus AI助手</h1>
                <p class="warning">前端尚未构建，使用基本界面</p>
                <textarea id="promptInput" placeholder="请输入您的问题..."></textarea>
                <button onclick="sendPrompt()">发送</button>
                <div id="output"></div>
            </div>
            
            <script>
                const outputDiv = document.getElementById('output');
                const promptInput = document.getElementById('promptInput');
                
                // 设置SSE连接
                const evtSource = new EventSource('/api/logs');
                evtSource.addEventListener('log', function(event) {
                    const data = JSON.parse(event.data);
                    outputDiv.innerHTML += data.content + '\\n';
                    outputDiv.scrollTop = outputDiv.scrollHeight;
                });
                
                // 发送提示
                function sendPrompt() {
                    const prompt = promptInput.value.trim();
                    if (!prompt) return;
                    
                    fetch('/api/prompt', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ prompt: prompt }),
                    })
                    .then(response => response.json())
                    .then(data => {
                        console.log('Success:', data);
                        promptInput.value = '';
                    })
                    .catch((error) => {
                        console.error('Error:', error);
                    });
                }
                
                // 监听回车键
                promptInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendPrompt();
                    }
                });
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content) 