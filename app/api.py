from fastapi import FastAPI, Body, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Annotated, List, Dict, Any
import json
import queue
import time
import asyncio
import os
import re
import glob
from pathlib import Path
from starlette.responses import Response, FileResponse
import uuid
import toml
import openai

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

# 当前任务的完整日志记录
current_task_logs = []

# 当前任务生成的文件列表
generated_files = []

# 上次任务摘要
last_task_summary = ""

# 摘要生成状态
summary_generation_status = {
    "in_progress": False,
    "message": ""
}

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

# 读取配置文件
try:
    config = toml.load("config/config.toml")
    openai_api_key = config.get("llm", {}).get("api_key", "")
    openai_model = config.get("llm", {}).get("model", "gpt-4o")
    if openai_api_key:
        openai.api_key = openai_api_key
except Exception as e:
    print(f"读取配置文件失败: {str(e)}")
    openai_api_key = ""
    openai_model = "gpt-3.5-turbo"

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
        
        # 添加到当前任务日志
        if processed_message != "处理完成":
            current_task_logs.append(processed_message)
        
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

def identify_generated_files(prompt):
    """从日志中识别生成的文件"""
    global generated_files, current_task_logs
    generated_files = []
    
    # 记录日志
    print(f"开始识别生成的文件，日志行数: {len(current_task_logs)}")
    
    # 将日志合并为一个字符串
    logs_text = "\n".join(current_task_logs)
    
    # 用于匹配文件路径的正则表达式模式
    file_patterns = [
        # 匹配常见的文件创建相关提示
        r'(?:创建|保存|生成|写入)(?:了|到)?(?:文件|文档|图表|报表|图片|数据)?\s*[\'"]?([\w\-./\\]+\.\w+)[\'"]?',
        # 匹配输出到文件的模式
        r'输出(?:结果|内容|数据)?\s*(?:到|至|存储在)?\s*[\'"]?([\w\-./\\]+\.\w+)[\'"]?',
        # 匹配保存文件的模式
        r'(?:保存|存储)(?:到|在|至)?\s*[\'"]?([\w\-./\\]+\.\w+)[\'"]?',
        # 匹配文件已创建/生成/保存的提示
        r'文件\s*[\'"]?([\w\-./\\]+\.\w+)[\'"]?\s*(?:已|成功)?(?:创建|生成|保存)',
        # 匹配文件名后跟随的路径模式
        r'文件名(?:为|是|:)?\s*[\'"]?([\w\-./\\]+\.\w+)[\'"]?',
        # 简单的文件路径匹配
        r'[\'"]?((?:\.?/|\.\\|(?:[a-zA-Z]:\\))?[\w\-./\\]+\.(?:txt|csv|xlsx?|docx?|pptx?|pdf|json|xml|html?|css|js|py|java|cpp|c|h|md|log|ini|conf|cfg|ya?ml|sql|db|sqlite|zip|rar|gz|tar|bz2|7z|png|jpe?g|gif|bmp|svg|mp[34]|wav|avi|mp4|mov|flv|wmv))[\'"]?'
    ]
    
    # 用于存储找到的文件路径
    file_paths = set()
    
    # 使用正则表达式从日志中提取文件路径
    for pattern in file_patterns:
        matches = re.finditer(pattern, logs_text)
        for match in matches:
            file_path = match.group(1).strip('"\'')
            if file_path and os.path.isfile(file_path):
                file_paths.add(file_path)
    
    # 如果没有找到文件，尝试在项目目录下查找最近修改的文件
    if not file_paths:
        print("未从日志中找到文件，尝试查找最近修改的文件")
        current_time = time.time()
        # 查找项目目录下最近1分钟内创建或修改的文件
        for root, _, files in os.walk("."):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_stat = os.stat(file_path)
                    # 检查文件是否在最近1分钟内创建或修改
                    if (current_time - file_stat.st_mtime < 60 or 
                        current_time - file_stat.st_ctime < 60):
                        # 排除日志和临时文件
                        if not (file.endswith('.log') or file.startswith('.') or 
                                'cache' in file_path.lower() or 'temp' in file_path.lower()):
                            file_paths.add(file_path)
                except Exception as e:
                    print(f"获取文件信息失败: {file_path}, 错误: {str(e)}")
    
    # 将找到的文件路径添加到生成的文件列表中
    for file_path in file_paths:
        try:
            # 获取文件的相对路径
            rel_path = os.path.relpath(file_path)
            generated_files.append(rel_path)
            print(f"找到生成的文件: {rel_path}")
        except Exception as e:
            print(f"处理文件路径失败: {file_path}, 错误: {str(e)}")
    
    print(f"找到 {len(generated_files)} 个生成的文件")
    return generated_files

# 为AI生成任务总结
async def generate_task_summary(prompt, logs):
    """使用OpenAI API生成任务执行结果的摘要"""
    global summary_generation_status, last_task_summary
    
    try:
        # 更新摘要生成状态
        summary_generation_status = {
            "in_progress": True,
            "message": "正在生成任务摘要..."
        }
        
        # 如果没有配置API密钥，则返回提示信息
        if not openai_api_key:
            last_task_summary = "无法生成详细摘要：未配置OpenAI API密钥。请在config/config.toml中配置。"
            summary_generation_status = {
                "in_progress": False,
                "message": "未配置API密钥，无法生成摘要"
            }
            return last_task_summary
            
        logs_text = "\n".join(logs)
        print(f"开始为任务生成摘要，日志长度：{len(logs_text)}")
        
        # 构建提示信息
        messages = [
            {"role": "system", "content": "你是一个任务执行分析专家，需要分析执行日志并提供简洁的总结。"},
            {"role": "user", "content": f"""请分析以下任务执行日志，并简洁地总结以下内容：
1. 任务的主要目标是什么
2. 任务是否成功完成
3. 生成了哪些文件及其主要内容和用途
4. 有没有遇到明显的错误或问题

请用中文回答，简明扼要，不超过300字。

任务提示: {prompt}

执行日志:
{logs_text[:50000]}  # 限制日志长度，防止超出token限制
"""}
        ]
        
        # 重试机制
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 使用异步方式调用OpenAI API
                response = await asyncio.to_thread(
                    openai.chat.completions.create,
                    model=openai_model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=500
                )
                
                # 提取摘要内容
                if response.choices and len(response.choices) > 0:
                    last_task_summary = response.choices[0].message.content
                    print("成功生成任务摘要")
                    break
                else:
                    retry_count += 1
                    await asyncio.sleep(1)  # 等待一秒后重试
            except Exception as e:
                error_message = f"重试 {retry_count+1}/{max_retries} 失败: {str(e)}"
                print(error_message)
                retry_count += 1
                await asyncio.sleep(2)  # 出错后等待稍长时间
                
                # 如果是最后一次重试失败，设置错误摘要
                if retry_count >= max_retries:
                    last_task_summary = f"无法生成详细摘要：连接API服务器失败，请检查网络或API配置。错误信息: {str(e)}"
        
    except Exception as e:
        print(f"生成任务摘要时出错: {str(e)}")
        import traceback
        print(traceback.format_exc())
        last_task_summary = f"生成摘要时出错: {str(e)}"
    finally:
        # 更新摘要生成状态
        summary_generation_status = {
            "in_progress": False,
            "message": ""
        }
        return last_task_summary

# 添加异步处理提示的函数
async def process_prompt_with_agent(agent, prompt):
    """使用代理处理提示词"""
    global current_task_logs, message_queue
    
    # 记录开始时间
    start_time = time.time()
    
    # 清空当前任务日志
    current_task_logs = []
    
    try:
        # 尝试运行代理
        result = await agent.run(prompt)
        
        # 处理结果
        if result:
            lines = result.split('\n')
            for line in lines:
                if line.strip():
                    # 添加到日志
                    log_interceptor(line)
        
        # 添加处理完成的消息
        log_interceptor("处理完成")
        
        # 识别生成的文件
        identify_generated_files(prompt)
        
        # 将所有日志合并为一个文本
        logs_text = "\n".join(current_task_logs)
        
        # 异步生成任务摘要
        asyncio.create_task(generate_task_summary(prompt, logs_text))
        
        # 记录耗时
        elapsed_time = time.time() - start_time
        print(f"任务处理完成，耗时: {elapsed_time:.2f}秒")
        
    except Exception as e:
        import traceback
        error_message = f"处理过程中出错: {str(e)}"
        print(error_message)
        print(traceback.format_exc())
        
        # 添加错误消息到日志
        log_interceptor(error_message)
        
        # 返回简化的错误消息给前端
        log_interceptor("处理完成")
        
        # 即使出错也尝试识别文件并生成摘要
        identify_generated_files(prompt)
        logs_text = "\n".join(current_task_logs)
        asyncio.create_task(generate_task_summary(prompt, logs_text))

# 添加新的API端点
@app.get("/api/files")
async def get_generated_files():
    """获取当前任务生成的文件列表和任务摘要"""
    file_list = []
    
    # 构建文件对象列表
    for file_path in generated_files:
        try:
            # 根据文件路径是字符串还是字典来获取文件信息
            actual_path = file_path if isinstance(file_path, str) else file_path.get("path", "")
            if not actual_path:
                continue
                
            file_info = os.stat(actual_path)
            file_name = os.path.basename(actual_path)
            file_list.append({
                "name": file_name,
                "path": actual_path,
                "size": file_info.st_size,
                "created": file_info.st_ctime
            })
        except Exception as e:
            path_str = file_path if isinstance(file_path, str) else str(file_path)
            print(f"获取文件信息失败: {path_str}, 错误: {str(e)}")
    
    # 返回文件列表和摘要
    return {
        "files": file_list,
        "summary": last_task_summary,
        "summary_status": summary_generation_status
    }

@app.get("/api/download/{file_name}")
async def download_file(file_name: str):
    """下载指定的文件"""
    # 查找匹配的文件
    # 兼容generated_files为字符串列表或字典列表的情况
    matching_files = []
    for f in generated_files:
        if isinstance(f, str):
            if os.path.basename(f) == file_name:
                matching_files.append(f)
        elif isinstance(f, dict) and f.get("name") == file_name:
            matching_files.append(f.get("path"))
    
    if not matching_files:
        raise HTTPException(status_code=404, detail=f"文件未找到: {file_name}")
    
    file_path = matching_files[0]
    
    # 检查文件是否存在
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    
    # 返回文件
    return FileResponse(
        path=file_path, 
        filename=file_name,
        media_type="application/octet-stream"
    )

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