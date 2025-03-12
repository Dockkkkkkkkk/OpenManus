from fastapi import FastAPI, Body, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Annotated, List, Dict, Any, Optional
import json
import queue
import time
import asyncio
import os
import re
import glob
from pathlib import Path
from starlette.responses import Response, FileResponse, RedirectResponse
import uuid
import toml
import openai
import sys
import random
import traceback
from datetime import datetime, timedelta
import platform
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from app.auth import Web, update_auth_config
from app.auth_routes import router as auth_router
# 导入任务管理路由
from app.routes.task_routes import router as task_router
# 导入页面路由
try:
    from app.routes import router as pages_router
except ImportError:
    # 如果从app.routes导入router失败，则直接创建一个空路由器
    from fastapi import APIRouter
    pages_router = APIRouter(tags=["pages"])
    print("警告: 无法导入页面路由，将使用空路由器")
try:
    from ai_file_identifier import AIFileIdentifier
except ImportError:
    print("注意: AI文件识别器模块未找到，将使用传统方法识别文件")
    pass
from app.services.task_service import task_service
from app.services.cos_service import cos_service

app = FastAPI()

# 重排注册顺序 - 先注册通用页面路由，再注册认证路由，最后是任务路由
# 注册页面路由
app.include_router(pages_router)
# 注册认证路由
app.include_router(auth_router)
# 注册任务路由 - 放在最后确保它有最高优先级
app.include_router(task_router)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量
generated_files = []
current_task_logs = []
pure_logs = []
last_task_summary = ""
completion_status = {"in_progress": False}
summary_generation_status = {"in_progress": False}
conversation_history = []
logs_processor_callback = None  # 存储日志处理回调函数

# 创建消息队列，用于存储日志消息
message_queue = asyncio.Queue()

# 创建OpenAI客户端
client = None

# 获取项目根目录
ROOT_DIR = Path(__file__).parent.parent
# 定义静态文件目录
STATIC_DIR = ROOT_DIR / "app" / "static"  # 更新静态文件目录路径
# 确保静态目录存在
STATIC_DIR.mkdir(exist_ok=True, parents=True)
# 定义前端构建输出目录
FRONTEND_DIR = STATIC_DIR
# 定义index.html路径
INDEX_HTML_PATH = FRONTEND_DIR / "index.html"
# 创建CSS和JS目录
CSS_DIR = STATIC_DIR / "css"
CSS_DIR.mkdir(exist_ok=True)
JS_DIR = STATIC_DIR / "js"
JS_DIR.mkdir(exist_ok=True)

# 认证相关设置
AUTH_REQUIRED = False  # 是否需要认证才能使用
AUTH_BASE_URL = "http://localhost:8000"  # 用户中心的基础URL

# 读取配置文件
try:
    if os.path.exists('config/config.toml'):
        print("正在加载配置文件: config/config.toml")
        config = toml.load('config/config.toml')
        
        # 读取 OpenAI 配置
        openai_api_key = config.get("llm", {}).get("api_key", "")
        openai_model = config.get("llm", {}).get("model", "gpt-4o")
        openai_base_url = config.get("llm", {}).get("base_url", "")
        
        # 设置认证选项
        auth_config = config.get('auth', {})
        AUTH_REQUIRED = auth_config.get("required", False)
        AUTH_BASE_URL = auth_config.get("base_url", "http://localhost:8000")
        AUTH_CLIENT_ID = auth_config.get("client_id", "openmanus")
        AUTH_CLIENT_SECRET = auth_config.get("client_secret", "")
        AUTH_SCOPE = auth_config.get("scope", "profile")
        
        # 打印认证配置详情
        print("=== 认证配置详情 ===")
        print(f"AUTH_REQUIRED = {AUTH_REQUIRED}")
        print(f"AUTH_BASE_URL = {AUTH_BASE_URL}")
        print(f"AUTH_CLIENT_ID = {AUTH_CLIENT_ID}")
        print(f"AUTH_CLIENT_SECRET = {'*' * len(AUTH_CLIENT_SECRET) if AUTH_CLIENT_SECRET else '(空)'}")
        print(f"AUTH_SCOPE = {AUTH_SCOPE}")
        print("====================")
        
        # 更新认证模块的配置
        update_auth_config(
            required=AUTH_REQUIRED, 
            base_url=AUTH_BASE_URL, 
            client_id=AUTH_CLIENT_ID, 
            client_secret=AUTH_CLIENT_SECRET
        )
        
        print(f"认证设置: 需要认证={AUTH_REQUIRED}, 认证服务URL={AUTH_BASE_URL}")
        
        # 设置OpenAI客户端配置
        if openai_api_key:
            # 确保安装了最新的openai库
            try:
                # 使用新的客户端方式
                if openai_base_url:
                    print(f"使用自定义API基础URL: {openai_base_url}")
                    client = openai.OpenAI(
                        api_key=openai_api_key,
                        base_url=openai_base_url
                    )
                    # 同时设置全局配置（兼容旧代码）
                    openai.api_key = openai_api_key
                    openai.base_url = openai_base_url
                else:
                    # 否则仅设置api_key
                    client = openai.OpenAI(api_key=openai_api_key)
                    openai.api_key = openai_api_key
                    
                # 测试客户端连接
                print("测试OpenAI客户端连接...")
                models = client.models.list()
                print(f"连接成功! 可用模型数量: {len(models.data) if hasattr(models, 'data') else '未知'}")
            except Exception as client_error:
                print(f"创建OpenAI客户端时出错: {str(client_error)}")
                # 尝试使用旧版兼容模式
                print("尝试使用兼容模式...")
                openai.api_key = openai_api_key
                if openai_base_url:
                    openai.api_base = openai_base_url
                client = None
        else:
            client = None
            print("警告: 未配置OpenAI API密钥")
except Exception as e:
    print(f"读取配置文件失败: {str(e)}")
    openai_api_key = ""
    openai_model = "gpt-3.5-turbo"
    openai_base_url = ""
    client = None

def log_interceptor(message):
    """拦截日志消息并将其添加到消息队列
    
    参数:
        message (str): 日志消息
    """
    global message_queue, current_task_logs, conversation_history, generated_files, logs_processor_callback
    
    if not message_queue:
        return

    try:
        # 移除行首可能存在的前缀和颜色标记
        # 例如：2024-01-01 12:34:56 | INFO | app.module: 
        cleaned_message = re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}.\d+\s+\|\s+\w+\s+\|\s+[\w\.]+:\s*', '', message)
        
        # 移除INFO/WARNING/ERROR前缀
        cleaned_message = re.sub(r'^(INFO|WARNING|ERROR)\s*[:|]\s*', '', cleaned_message)
        cleaned_message = re.sub(r'^(INFO|WARNING|ERROR)\s*\|\s*', '', cleaned_message)
        
        # 移除其他可能的前缀，如 | INFO | 
        cleaned_message = re.sub(r'^\|\s*\w+\s*\|\s*', '', cleaned_message)
        
        # 移除一些特殊的标记符，可能导致前端显示问题
        cleaned_message = cleaned_message.rstrip('|').strip()
        
        # 打印调试信息
        print(f"日志拦截器: 原始消息 [{message[:50]}...] -> 清理后 [{cleaned_message[:50]}...]")
        
        # 如果有日志处理回调函数，调用它
        if logs_processor_callback and callable(logs_processor_callback):
            logs_processor_callback(cleaned_message)
        
        # 检查是否包含文件生成信息
        file_msg = None
        file_patterns = [
            r'(?:saved|created|generated|written)(?:\s*to)?\s*(?:file)?\s*[:]?\s*(?:as|to)?[:]?\s*[\'"]?(?P<filepath>[\w\-./\\]+\.\w+)[\'"]?',
            r'file\s*(?:saved|created|generated)\s*[:]?\s*[\'"]?(?P<filepath>[\w\-./\\]+\.\w+)[\'"]?',
            r'generated file\s*[:]?\s*[\'"]?(?P<filepath>[\w\-./\\]+\.\w+)[\'"]?'
        ]
        
        for pattern in file_patterns:
            match = re.search(pattern, cleaned_message)
            if match:
                file_path = match.group('filepath')
                if file_path and os.path.exists(file_path):
                    file_msg = {"content": cleaned_message, "file": file_path}
                    if file_path not in generated_files:
                        generated_files.append(file_path)
                        print(f"识别到新生成的文件: {file_path}")
                    break
        
        # 将处理后的消息放入队列
        if file_msg:
            message_queue.put_nowait(file_msg)
        else:
            message_queue.put_nowait({
                "content": cleaned_message
            })
        
        # 添加到当前任务日志
        if cleaned_message != "处理完成":
            current_task_logs.append(cleaned_message)
        
        # 保存到对话历史
        if cleaned_message and isinstance(cleaned_message, str):
            conversation_history.append({"role": "system", "content": cleaned_message})
            # 限制历史记录长度
            if len(conversation_history) > 100:
                conversation_history.pop(0)
    except Exception as e:
        print(f"Failed to add message to queue: {str(e)}")

async def event_generator():
    """生成服务器发送事件流"""
    global message_queue
    
    # 创建此连接的唯一标识符
    connection_id = str(uuid.uuid4())
    print(f"新的SSE连接已建立: {connection_id}")
    
    # 记录已发送消息的ID
    sent_message_ids = set()
    
    # 发送初始连接事件
    yield "event: connect\ndata: {}\n\n"
    
    # 发送一个欢迎消息
    try:
        welcome_msg = "已连接到OpenManus系统"
        message_id = str(uuid.uuid4())
        yield f"data: {{\"id\": \"{message_id}\", \"type\": \"log\", \"message\": \"{welcome_msg}\"}}\n\n"
    except Exception as e:
        print(f"欢迎消息发送错误: {str(e)}")
    
    # 创建一个副本队列，不影响其他连接
    private_queue = asyncio.Queue()
    
    # 任务运行状态
    running = True
    
    while running:
        try:
            # 获取所有队列中的消息，但不重复发送
            try:
                # 从主队列获取一条消息
                try:
                    message = await asyncio.wait_for(message_queue.get(), timeout=0.1)
                    
                    # 生成消息ID（基于内容和时间戳）
                    message_id = str(uuid.uuid4())
                    
                    # 如果消息带有任务完成标记，设置running为False
                    if isinstance(message, dict) and message.get("content") == "处理完成":
                        print(f"连接 {connection_id} 检测到任务完成信号")
                        running = False
                        # 发送完成事件
                        completion_id = str(uuid.uuid4())
                        yield f"data: {{\"id\": \"{completion_id}\", \"type\": \"completion\"}}\n\n"
                    
                    # 将消息放入私有队列
                    if message_id not in sent_message_ids:
                        sent_message_ids.add(message_id)
                        # 将原始消息和消息ID一起放入队列
                        await private_queue.put((message, message_id))
                    
                except asyncio.TimeoutError:
                    # 超时，没有新消息
                    pass
                    
                # 从私有队列获取一条消息并发送
                if not private_queue.empty():
                    message, msg_id = private_queue.get_nowait()
                    if message:
                        # 将内部消息格式转换为前端期望的格式
                        try:
                            if isinstance(message, dict):
                                content = message.get("content", "")
                                formatted_message = {
                                    "id": msg_id,
                                    "type": "log",
                                    "message": content
                                }
                                
                                # 如果是文件更新消息，转换为file类型
                                if "file" in message and message.get("file"):
                                    formatted_message["type"] = "file"
                                    formatted_message["filename"] = message.get("file")
                                
                                message_json = json.dumps(formatted_message)
                                print(f"连接 {connection_id} 发送消息: {str(formatted_message)[:50]}...")
                                yield f"data: {message_json}\n\n"
                            else:
                                # 简单字符串消息
                                formatted_message = {
                                    "id": msg_id,
                                    "type": "log",
                                    "message": str(message)
                                }
                                message_json = json.dumps(formatted_message)
                                yield f"data: {message_json}\n\n"
                        except Exception as json_err:
                            print(f"JSON序列化错误: {str(json_err)}, 消息: {str(message)[:100]}")
                else:
                    # 队列为空，短暂等待
                    await asyncio.sleep(0.1)
                    
            except Exception as queue_err:
                print(f"队列操作错误: {str(queue_err)}")
                await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"生成事件错误: {str(e)}")
            import traceback
            traceback.print_exc()
            # 发生错误后短暂等待
            await asyncio.sleep(1)
    
    print(f"SSE连接 {connection_id} 已结束")

# 添加event_generator的辅助方法
# 发送日志消息
def event_generator_send_log(message, level="info"):
    try:
        if message_queue:
            message_queue.put_nowait({
                "content": message,
                "level": level
            })
    except Exception as e:
        print(f"发送日志消息错误: {str(e)}")

# 发送文件通知
def event_generator_send_file(file_path):
    try:
        if message_queue:
            message_queue.put_nowait({
                "content": f"已识别文件: {file_path}",
                "file": file_path
            })
    except Exception as e:
        print(f"发送文件通知错误: {str(e)}")

# 发送完成事件
def event_generator_send_completion():
    try:
        if message_queue:
            message_queue.put_nowait({
                "content": "处理完成"
            })
    except Exception as e:
        print(f"发送完成事件错误: {str(e)}")

# 设置静态方法
event_generator.send_log = event_generator_send_log
event_generator.send_file = event_generator_send_file
event_generator.send_completion = event_generator_send_completion

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
        f.write('<!DOCTYPE html>\n')
        f.write('<html lang="zh-CN">\n')
        f.write('<head>\n')
        f.write('    <meta charset="UTF-8">\n')
        f.write('    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n')
        f.write('    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">\n')
        f.write('    <meta http-equiv="Pragma" content="no-cache">\n')
        f.write('    <meta http-equiv="Expires" content="0">\n')
        f.write('    <title>OpenManus - 智能AI代码生成器</title>\n')
        f.write('    <link rel="stylesheet" href="/static/css/styles.css">\n')
        f.write('</head>\n')
        f.write('<body>\n')
        f.write('    <header class="header">\n')
        f.write('        <h1>OpenManus</h1>\n')
        f.write('    </header>\n')
        f.write('    <div class="main-container">\n')
        f.write('        <div class="input-panel">\n')
        f.write('            <h2 class="panel-header">任务设置</h2>\n')
        f.write('            <div class="input-container">\n')
        f.write('                <textarea id="prompt" placeholder="请输入您想要完成的任务描述..."></textarea>\n')
        f.write('                <button id="submit">执行任务</button>\n')
        f.write('                <div id="processing-indicator" class="processing-indicator">处理中，请稍候...</div>\n')
        f.write('            </div>\n')
        f.write('        </div>\n')
        f.write('        <div class="log-panel">\n')
        f.write('            <div class="tab-container">\n')
        f.write('                <div class="tab active" data-target="logs-tab">执行日志</div>\n')
        f.write('                <div class="tab" data-target="files-tab">生成文件</div>\n')
        f.write('            </div>\n')
        f.write('            <div id="logs-tab" class="tab-content active">\n')
        f.write('                <div id="logs" class="logs-container"></div>\n')
        f.write('            </div>\n')
        f.write('            <div id="files-tab" class="tab-content">\n')
        f.write('                <div id="files" class="files-container">\n')
        f.write('                    <div id="no-files-message" class="no-files-message">暂无生成文件</div>\n')
        f.write('                </div>\n')
        f.write('            </div>\n')
        f.write('        </div>\n')
        f.write('    </div>\n')
        f.write('    <script src="/static/js/main.js"></script>\n')
        f.write('</body>\n')
        f.write('</html>\n')

@app.get("/api/logs")
@Web(auth_required=False)  # 不需要认证 - 日志流可以公开访问
async def stream_logs(request: Request):
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

@app.get("/api/events")
@Web(auth_required=False)  # 不需要认证 - 事件流可以公开访问
async def stream_events(request: Request):
    """提供事件流端点（替代/api/logs，供前端使用）"""
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
@Web()  # 默认需要认证
async def handle_prompt(request: Request, prompt_data: dict):
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
            
            # 获取默认模型
            from app.config import config
            default_model = config.llm["default"].model
            
            # 异步执行代理，使用配置的默认模型
            asyncio.create_task(process_prompt_with_agent(prompt, default_model, None))
            
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

async def identify_generated_files(logs_text, prompt=""):
    """使用AI识别生成的文件
    
    该函数会同时使用AI模型和正则表达式识别日志中提到的生成文件，
    并返回两种方法识别结果的并集，以提高识别的覆盖率。
    
    Args:
        logs_text: 纯净的日志文本内容
        prompt: 用户提示，提供上下文（可选）
    """
    all_files = set()  # 使用集合存储所有识别到的文件，自动去重
    
    try:
        print(f"[文件识别] 开始识别生成的文件，日志长度: {len(logs_text)}")
        
        # 尝试使用AI识别文件
        ai_files = []
        try:
            print("[文件识别] 正在导入AI文件识别器...")
            
            # 导入AI文件识别器
            from ai_file_identifier import AIFileIdentifier
            print("[文件识别] AI文件识别器导入成功")
            
            try:
                print("[文件识别] 创建识别器实例...")
                identifier = AIFileIdentifier()
                
                print(f"[文件识别] 开始分析日志，长度：{len(logs_text)}")
                # 使用当前事件循环执行AI识别
                ai_files = await identifier.identify_files(prompt=prompt, logs=logs_text)
                
                print(f"[文件识别] AI识别到 {len(ai_files)} 个文件")
                
                # 添加AI识别的文件
                for file in ai_files:
                    if os.path.exists(file):
                        all_files.add(file)
            except Exception as e:
                print(f"[文件识别] AI识别过程出错: {str(e)}")
                import traceback
                traceback.print_exc()
        except ImportError:
            print("[文件识别] AI文件识别器不可用")
            
        # 使用正则表达式方法识别文件
        print("[文件识别] 使用正则表达式识别文件")
        regex_files = _regex_identify_files(logs_text)
        
        # 添加正则表达式识别的文件
        for file in regex_files:
            if os.path.exists(file):
                all_files.add(file)
        
        # 转换集合为列表
        identified_files = list(all_files)
        print(f"[文件识别] 总共识别到 {len(identified_files)} 个文件")
        return identified_files
    
    except Exception as e:
        print(f"[文件识别] 出错: {str(e)}")
        traceback.print_exc()
        return []

def _regex_identify_files(logs_text):
    """使用正则表达式从日志中识别文件
    
    Args:
        logs_text: 纯净的日志文本内容
        
    Returns:
        生成的文件列表
    """
    print("使用正则表达式方法识别文件")
    generated_files = []
    
    # 文件识别正则表达式
    file_patterns = [
        r'(?:saved|created|generated|written)(?:\s*to)?\s*(?:file)?\s*[:]?\s*(?:as|to)?[:]?\s*[\'"]?(?P<filepath>[\w\-./\\]+\.\w+)[\'"]?',
        r'file\s*(?:saved|created|generated)\s*[:]?\s*[\'"]?(?P<filepath>[\w\-./\\]+\.\w+)[\'"]?',
        r'generated file\s*[:]?\s*[\'"]?(?P<filepath>[\w\-./\\]+\.\w+)[\'"]?'
    ]
    
    # 使用每个正则表达式模式搜索
    import re
    for pattern in file_patterns:
        matches = re.finditer(pattern, logs_text)
        for match in matches:
            try:
                file_path = match.group("filepath").strip().strip('"\'')
                # 验证文件是否存在
                if os.path.exists(file_path):
                    # 避免重复添加
                    if file_path not in generated_files:
                        # 排除一些系统文件和临时文件
                        if not (file_path.startswith(".") or 
                               file_path.endswith(".pyc") or 
                               "__pycache__" in file_path or
                               "FETCH_HEAD" in file_path):
                            generated_files.append(file_path)
                            print(f"找到生成的文件: {file_path}")
            except Exception as e:
                print(f"处理文件路径失败: {file_path if 'file_path' in locals() else 'unknown'}, 错误: {str(e)}")
    
    print(f"正则表达式识别到 {len(generated_files)} 个文件")
    return generated_files

# 为AI生成任务总结
async def generate_task_summary(prompt, logs):
    """使用OpenAI API生成任务执行结果的摘要
    
    当日志内容过多时，采用分段摘要再合并的策略：
    1. 将日志分成多个段落
    2. 为每个段落生成摘要
    3. 将所有段落摘要合并，再生成最终摘要
    4. 所有步骤均采用流式响应，避免超时
    
    参数:
        prompt (str): 用户提示词
        logs (list): 日志内容列表
        
    返回:
        str: 生成的摘要
    """
    global summary_generation_status, last_task_summary, client, message_queue
    
    try:
        summary_generation_status = {
            "in_progress": True,
            "message": "正在生成任务摘要..."
        }
        
        if not openai_api_key:
            last_task_summary = "无法生成详细摘要：未配置OpenAI API密钥。请在config/config.toml中配置。"
            summary_generation_status = {
                "in_progress": False,
                "message": "未配置API密钥，无法生成摘要"
            }
            return last_task_summary
            
        # 日志文本总长度
        logs_text = "\n".join(logs)
        total_length = len(logs_text)
        print(f"开始为任务生成摘要，原始日志长度：{total_length}")
        
        # 分段大小，以字符为单位
        segment_size = 20000  # 每段最多20000个字符
        
        # 如果日志过长，需要分段处理
        need_segmentation = total_length > segment_size
        
        # 通知前端开始生成摘要
        message_queue.put_nowait("开始生成摘要...")
        
        if need_segmentation:
            print(f"日志过长，将分段处理，共 {(total_length + segment_size - 1) // segment_size} 段")
            message_queue.put_nowait(f"日志较长（{total_length}字符），正在分段分析...")
            
            # 分段处理
            segments = []
            for i in range(0, total_length, segment_size):
                segments.append(logs_text[i:i + segment_size])
            
            # 为每段生成摘要
            segment_summaries = []
            for i, segment in enumerate(segments):
                message_queue.put_nowait(f"正在分析第 {i+1}/{len(segments)} 段日志...")
                print(f"生成第 {i+1}/{len(segments)} 段摘要，长度：{len(segment)}")
                
                segment_summary = await _generate_segment_summary(
                    segment, 
                    prompt, 
                    f"第 {i+1}/{len(segments)} 段",
                    i == 0  # 是否是第一段
                )
                
                if segment_summary:
                    segment_summaries.append(segment_summary)
                    message_queue.put_nowait(f"第 {i+1} 段分析完成")
                else:
                    message_queue.put_nowait(f"第 {i+1} 段分析失败")
            
            # 如果有多段摘要，合并生成最终摘要
            if len(segment_summaries) > 1:
                message_queue.put_nowait("正在整合所有段落的分析结果...")
                print("生成最终摘要，整合所有段落分析")
                
                final_summary = await _generate_final_summary(segment_summaries, prompt)
                
                if final_summary:
                    last_task_summary = final_summary
                    message_queue.put_nowait("摘要生成完成")
                    print("成功生成最终任务摘要")
                else:
                    # 如果最终摘要生成失败，使用所有段落摘要的拼接
                    joined_summary = "\n\n".join([
                        f"【第 {i+1}/{len(segment_summaries)} 段分析】\n{summary}" 
                        for i, summary in enumerate(segment_summaries)
                    ])
                    last_task_summary = joined_summary
                    message_queue.put_nowait("摘要整合过程中出现问题，已提供各段分析结果")
                    print("最终摘要生成失败，使用分段摘要拼接")
            elif len(segment_summaries) == 1:
                # 只有一段摘要
                last_task_summary = segment_summaries[0]
                print("只有一段摘要，直接使用")
            else:
                # 没有摘要
                error_msg = "所有段落分析均失败，无法生成摘要"
                last_task_summary = error_msg
                message_queue.put_nowait(error_msg)
                print(error_msg)
        else:
            # 日志不需要分段处理，直接生成摘要
            print("日志长度适中，直接生成摘要")
            summary = await _generate_segment_summary(logs_text, prompt, "完整", True)
            
            if summary:
                last_task_summary = summary
                message_queue.put_nowait("摘要生成完成")
                print("成功生成任务摘要")
            else:
                error_msg = "摘要生成失败"
                last_task_summary = error_msg
                message_queue.put_nowait(error_msg)
                print(error_msg)
        
    except Exception as e:
        error_msg = f"生成摘要时出错: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        last_task_summary = error_msg
        message_queue.put_nowait(error_msg)
        
    finally:
        summary_generation_status = {
            "in_progress": False,
            "message": ""
        }
        return last_task_summary

async def _generate_segment_summary(segment_text, prompt, segment_label, is_first_segment):
    """为单个日志段落生成摘要"""
    max_retries = 3
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"尝试生成{segment_label}摘要 (尝试 {attempt}/{max_retries})...")
            
            # 构建系统消息和用户消息
            system_message = "你是一个任务执行分析专家，需要详细分析执行日志并提供全面的总结。你擅长识别关键流程、生成的文件以及可能的问题点，并提供有价值的见解。"
            
            # 根据不同段落构建不同的提示
            if is_first_segment:
                user_message = f"请分析以下任务执行日志{segment_label}，提供一个全面详细的总结分析。包含以下方面：主要目标、执行流程、成功标准、生成的文件、遇到的问题、改进建议等。请自由组织内容，提供有深度的分析：\n\n{segment_text}\n\n提示词：{prompt}"
            else:
                user_message = f"请继续分析以下任务执行日志{segment_label}，重点关注这部分日志中的新信息，避免与前面重复。请关注：执行过程中的变化、新生成的文件、遇到的问题等：\n\n{segment_text}\n\n提示词：{prompt}"
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ]
            
            # 使用流式请求
            stream_response = client.chat.completions.create(
                model=openai_model,
                messages=messages,
                temperature=0.2,
                max_tokens=1000,
                stream=True
            )
            
            # 收集摘要内容
            summary_content = ""
            prefix = f"【{segment_label}分析】" if segment_label != "完整" else ""
            
            if prefix:
                message_queue.put_nowait(prefix)
                
            async for content in _aiter_stream(stream_response):
                summary_content += content
                message_queue.put_nowait(content)
            
            if summary_content.strip():
                if prefix:
                    return f"{prefix}\n{summary_content}"
                return summary_content
            else:
                raise Exception("生成的摘要内容为空")
                
        except Exception as e:
            print(f"{segment_label}摘要尝试 {attempt} 失败: {str(e)}")
            if attempt == max_retries:
                return None
            await asyncio.sleep(2)
    
    return None

async def _generate_final_summary(segment_summaries, prompt):
    """根据所有段落摘要生成最终摘要"""
    max_retries = 3
    
    # 合并所有段落摘要
    all_summaries = "\n\n".join(segment_summaries)
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"尝试生成最终整合摘要 (尝试 {attempt}/{max_retries})...")
            
            # 构建系统消息和用户消息
            system_message = "你是一个信息整合专家，擅长将多段分析结果整合为一份连贯、全面且有洞察力的报告。请保留所有重要细节，但避免重复信息。"
            
            user_message = f"请将以下多段任务分析结果整合为一份完整、连贯的报告。你需要保留所有关键信息，但要避免重复。请确保最终报告结构清晰，包含：主要目标、执行过程、成功结果、生成的文件、遇到的问题和改进建议等内容。\n\n{all_summaries}\n\n原始任务提示词：{prompt}"
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ]
            
            # 使用流式请求
            stream_response = client.chat.completions.create(
                model=openai_model,
                messages=messages,
                temperature=0.2,
                max_tokens=1500,
                stream=True
            )
            
            # 发送分隔符
            message_queue.put_nowait("\n\n【最终整合分析】\n")
            
            # 收集摘要内容
            summary_content = ""
            async for content in _aiter_stream(stream_response):
                summary_content += content
                message_queue.put_nowait(content)
            
            if summary_content.strip():
                return f"【最终整合分析】\n{summary_content}"
            else:
                raise Exception("生成的最终摘要内容为空")
                
        except Exception as e:
            print(f"最终摘要尝试 {attempt} 失败: {str(e)}")
            if attempt == max_retries:
                return None
            await asyncio.sleep(2)
    
    return None

async def _aiter_stream(stream):
    """处理流式响应的辅助函数"""
    try:
        for chunk in stream:
            if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
    except Exception as e:
        print(f"流式迭代出错: {str(e)}")
        import traceback
        traceback.print_exc()
        yield f"生成过程中发生错误: {str(e)}"

# 修改process_prompt_with_agent方法，支持用户信息
async def process_prompt_with_agent(prompt, model=None, user_info=None):
    """处理提示并记录日志，支持用户信息"""
    global generated_files, current_task_logs, pure_logs, logs_processor_callback
    
    try:
        # 如果未提供模型，使用配置中的默认模型
        if model is None:
            from app.config import config
            model = config.llm["default"].model
        
        # 创建任务记录
        user_id = user_info.get('user_id', 'anonymous') if user_info else 'anonymous'
        
        # 导入任务服务（延迟导入避免循环引用）
        from app.services.task_service import task_service
        
        # 记录任务开始信息
        task_id = await task_service.create_task(user_id, prompt)
        await task_service.update_task_status(task_id, "running")
        
        # 记录任务开始信息
        log_message = f"任务开始 - 模型: {model} - 任务ID: {task_id}"
        
        # 添加用户信息（如果有）
        if user_info:
            log_message += f" - 用户: {user_info.get('username', '未知用户')}"
        
        # 暂存到内存而不是立即上传到数据库
        current_task_logs.append(log_message)
        
        # 发送到前端
        event_generator.send_log(log_message, level="system")
        
        # 重置任务状态
        generated_files = []
        current_task_logs = []
        pure_logs = []
        
        # 用于跟踪分段任务的状态
        task_status = {
            "current_logs_length": 0,
            "segment_size": 20000,  # 每20000个字符触发一次处理
            "segments": []
        }
        
        # 记录输入的提示
        print(f"执行任务: {prompt}")
        
        # 添加日志拦截处理
        def logs_processor(message):
            # 清理日志内容
            cleaned_log = message  # 日志已在log_interceptor中清理过
            
            # 添加到纯净日志和任务日志
            if cleaned_log:
                pure_logs.append(cleaned_log)
                current_task_logs.append(cleaned_log)
                
                # 注释掉实时上传日志的代码，改为只在内存中积累日志
                # 异步方式记录到数据库
                # asyncio.create_task(task_service.append_task_logs(task_id, cleaned_log))
                
                # 检查日志长度并触发处理
                task_status["current_logs_length"] += len(cleaned_log)
                if task_status["current_logs_length"] >= task_status["segment_size"]:
                    # 获取当前日志内容
                    current_segment = "\n".join(pure_logs)
                    task_status["segments"].append(current_segment)
                    
                    # 启动文件识别任务
                    print(f"触发文件识别: 日志长度达到 {task_status['current_logs_length']} 字符")
                    asyncio.create_task(process_segment(current_segment, len(task_status["segments"])))
                    
                    # 重置当前累计长度
                    task_status["current_logs_length"] = 0
                    pure_logs.clear()  # 使用clear()而不是重新赋值
        
        # 定义段处理函数
        async def process_segment(segment_text, segment_num):
            try:
                print(f"开始处理第 {segment_num} 段日志，长度: {len(segment_text)} 字符")
                
                # 识别文件
                segment_files = await identify_generated_files(segment_text, prompt)
                if segment_files:
                    print(f"第 {segment_num} 段识别到 {len(segment_files)} 个文件")
                    for file in segment_files:
                        if file not in generated_files:
                            generated_files.append(file)
                            print(f"添加新文件: {file}")
                            
                            # 上传文件到COS并记录到数据库
                            try:
                                # 上传文件到COS
                                print(f"上传文件到COS: {file}")
                                uploaded_file = await task_service.upload_local_file(
                                    task_id=task_id,
                                    filepath=file
                                )
                                
                                # 发送文件通知给前端
                                if uploaded_file:
                                    event_generator.send_file(uploaded_file["filename"])
                                    print(f"文件上传成功: {uploaded_file['filename']} -> {uploaded_file['cos_url']}")
                            except Exception as upload_error:
                                print(f"上传文件失败: {str(upload_error)}")
                                # 失败时仍然发送文件信息
                                event_generator.send_file(os.path.basename(file))
                else:
                    print(f"第 {segment_num} 段未识别到文件")
            except Exception as e:
                print(f"处理第 {segment_num} 段时出错: {str(e)}")
        
        # 设置全局回调
        logs_processor_callback = logs_processor
        
        # 创建并配置智能体
        from app.agent.swe import SWEAgent
        
        # 根据模型创建智能体
        agent = SWEAgent()
        agent.llm.model = model
        
        # 如果用户已登录，添加用户信息到智能体
        if user_info:
            agent.user_info = user_info
        
        # 执行智能体任务
        await agent.run(prompt)
        
        # 处理剩余日志
        if pure_logs and task_status["current_logs_length"] > 0:
            current_segment = "\n".join(pure_logs)
            print(f"处理剩余日志片段, 长度: {task_status['current_logs_length']} 字符")
            await process_segment(current_segment, len(task_status["segments"]) + 1)
        
        # 识别所有文件
        if current_task_logs:
            all_logs = "\n".join(current_task_logs)
            print(f"执行最终文件识别，总日志长度: {len(all_logs)} 字符")
            final_files = await identify_generated_files(all_logs, prompt)
            for file in final_files:
                if file not in generated_files:
                    generated_files.append(file)
                    
                    # 上传文件到COS并记录到数据库
                    try:
                        # 上传文件到COS
                        print(f"上传最终文件到COS: {file}")
                        uploaded_file = await task_service.upload_local_file(
                            task_id=task_id,
                            filepath=file
                        )
                        
                        # 发送文件通知给前端
                        if uploaded_file:
                            event_generator.send_file(uploaded_file["filename"])
                            print(f"最终文件上传成功: {uploaded_file['filename']} -> {uploaded_file['cos_url']}")
                    except Exception as upload_error:
                        print(f"上传最终文件失败: {str(upload_error)}")
                        # 失败时仍然发送文件信息
                        event_generator.send_file(os.path.basename(file))
        
        # 清除回调
        logs_processor_callback = None
        
        # 将所有积累的日志一次性上传到COS
        if current_task_logs:
            try:
                # 合并所有日志
                all_logs_text = "\n".join(current_task_logs)
                print(f"任务完成，一次性上传所有日志，总长度: {len(all_logs_text)} 字符")
                
                # 上传日志到COS
                log_url = await cos_service.upload_text(
                    f"task_{task_id}_complete_log.txt", 
                    all_logs_text, 
                    f"tasks/{task_id}/logs/"
                )
                
                # 更新任务的日志URL
                await task_service.update_task_log_url(task_id, log_url)
                print(f"任务日志上传成功: {log_url}")
            except Exception as log_error:
                print(f"上传任务完整日志失败: {str(log_error)}")
                # 日志上传失败不中断流程
        
        # 更新任务状态为完成
        await task_service.update_task_status(task_id, "completed")
        
        # 发送完成标记
        event_generator.send_completion()
        
        # 返回生成的文件列表和任务ID
        return {"files": generated_files, "task_id": task_id}
    except Exception as e:
        error_msg = f"处理任务时出错: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        
        # 更新任务状态为失败
        if 'task_id' in locals():
            # 检查是否有积累的日志需要上传
            if 'current_task_logs' in locals() and current_task_logs:
                try:
                    # 合并所有日志并添加错误信息
                    current_task_logs.append(f"ERROR: {error_msg}")
                    all_logs_text = "\n".join(current_task_logs)
                    print(f"任务失败，上传错误日志，总长度: {len(all_logs_text)} 字符")
                    
                    # 上传日志到COS
                    log_url = await cos_service.upload_text(
                        f"task_{task_id}_error_log.txt", 
                        all_logs_text, 
                        f"tasks/{task_id}/logs/"
                    )
                    print(f"错误日志上传成功: {log_url}")
                except Exception as log_error:
                    print(f"上传错误日志失败: {str(log_error)}")
            
            # 更新任务状态
            await task_service.update_task_status(task_id, "failed", str(e))
        
        # 发送错误消息
        event_generator.send_log(error_msg, level="error")
        
        # 即使出错也尝试发送完成标记
        event_generator.send_completion()
        
        # 重新抛出异常
        raise

# 添加新的API端点
@app.get("/api/files")
@Web()  # 默认需要认证
async def get_generated_files(request: Request):
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

@app.get("/api/files/{file_id}/download")
@Web(auth_required=False)  # 暂时不要求认证，方便测试
async def download_file(request: Request, file_id: int):
    """下载任务文件"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"尝试下载文件: ID={file_id}")
    
    try:
        # 从文件服务或本地获取文件
        file_data = await task_service.get_file(str(file_id))  # 确保转换为字符串
        logger.debug(f"获取到文件数据: {file_data}")
        
        if not file_data:
            logger.warning(f"文件不存在: ID={file_id}")
            return JSONResponse(
                status_code=404, 
                content={"error": f"文件不存在 ID={file_id}"}
            )
            
        # 文件信息
        filename = file_data.get("filename", f"file_{file_id}")
        file_url = file_data.get("cos_url") or file_data.get("file_url", "")
        
        logger.info(f"文件信息: 名称={filename}, URL={file_url}")
            
        # 如果文件在COS上，重定向到COS URL
        if file_url and file_url.startswith("http"):
            logger.info(f"重定向到COS URL: {file_url}")
            return RedirectResponse(file_url)
            
        # 如果文件在本地，返回本地文件
        file_path = file_data.get("local_path", "")
        if file_path and os.path.exists(file_path):
            logger.info(f"从本地路径返回文件: {file_path}")
            return FileResponse(
                path=file_path,
                filename=filename,
                media_type=file_data.get("content_type", "application/octet-stream")
            )
            
        # 如果找不到文件路径，检查content字段
        if "content" in file_data and file_data["content"]:
            logger.info(f"从content字段获取文件内容")
            content = file_data["content"]
            # 返回文件内容作为流式响应
            return StreamingResponse(
                iter([content]), 
                media_type=file_data.get("content_type", "application/octet-stream"),
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
            
        # 如果找不到文件，返回404
        logger.warning(f"文件无法访问: ID={file_id}")
        return JSONResponse(
            status_code=404, 
            content={"error": f"文件无法访问 ID={file_id}"}
        )
            
    except Exception as e:
        logger.error(f"下载文件失败: ID={file_id}, 错误: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500, 
            content={"error": f"下载文件失败: {str(e)}"}
        )

@app.get("/api/download/{file_name}")
@Web()  # 默认需要认证
async def download_file_query(request: Request, file_name: str):
    """下载指定的文件（查询参数版本）"""
    # 查找匹配的文件
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
@Web()  # 默认需要认证
async def get_history(request: Request):
    """获取对话历史记录"""
    return {"history": conversation_history}

# 挂载静态文件目录
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/api/tasks")
@Web(auth_required=False)
async def get_all_tasks(request: Request):
    """获取所有任务列表，包括数据库和内存中的任务"""
    try:
        # 从请求状态中获取用户信息
        user_info = getattr(request.state, "user", None)
        user_id = user_info.get("user_id", "test_user") if user_info else "test_user"
            
        # 使用任务服务获取所有任务
        tasks = await task_service.get_user_tasks(user_id, 100, 0)
        
        # 将日期时间对象转换为字符串
        for task in tasks:
            if "created_at" in task and isinstance(task["created_at"], datetime):
                task["created_at"] = task["created_at"].isoformat()
            if "updated_at" in task and isinstance(task["updated_at"], datetime):
                task["updated_at"] = task["updated_at"].isoformat()
            if "completed_at" in task and isinstance(task["completed_at"], datetime):
                task["completed_at"] = task["completed_at"].isoformat()
        
        return tasks
    except Exception as e:
        return JSONResponse(
            {"error": f"无法获取任务列表: {str(e)}"},
            status_code=500
        )

@app.get("/api/tasks/{task_id}")
@Web(auth_required=False)
async def get_task_detail(request: Request, task_id: int):
    """获取单个任务的详细信息（通过路径参数）- 备用方法，可能存在参数传递冲突问题"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"请求获取任务详情: ID={task_id}")
    try:
        # 从请求状态中获取用户信息
        user_info = getattr(request.state, "user", None)
        user_id = user_info.get("user_id", "test_user") if user_info else "test_user"
        logger.debug(f"当前用户: {user_id}, 请求任务ID: {task_id}")
        
        # 使用位置参数传递task_id，避免参数名冲突
        task = await task_service.get_task(int(task_id))
        
        # 检查返回结果
        if not task:
            logger.warning(f"找不到任务: ID={task_id}")
            return JSONResponse(
                {"error": f"找不到任务: {task_id}"},
                status_code=404
            )
        
        # 检查是否返回了错误信息
        if task.get("error"):
            logger.error(f"获取任务失败: {task.get('error')}")
            return JSONResponse(
                {"error": task.get("error")},
                status_code=500
            )
        
        # 将日期时间对象转换为字符串
        for date_field in ["created_at", "updated_at", "completed_at"]:
            if date_field in task and isinstance(task[date_field], datetime):
                task[date_field] = task[date_field].isoformat()
        
        # 处理日志内容
        if "logs" in task and isinstance(task["logs"], bytes):
            try:
                task["logs"] = task["logs"].decode("utf-8", errors="replace")
            except Exception as decode_error:
                logger.error(f"解码日志失败: {str(decode_error)}")
                task["logs"] = "日志内容无法解码"
        elif not task.get("logs"):
            task["logs"] = "暂无日志信息"
        
        # 确保文件列表存在
        if "files" not in task or not task["files"]:
            task["files"] = []
        
        # 处理文件列表中的时间戳
        if isinstance(task["files"], list):
            for file in task["files"]:
                if "created_at" in file and isinstance(file["created_at"], datetime):
                    file["created_at"] = file["created_at"].isoformat()
        
        logger.info(f"成功获取任务详情: ID={task_id}")
        return task
    except Exception as e:
        logger.error(f"获取任务详情失败，意外错误: {str(e)}", exc_info=True)
        return JSONResponse(
            {"error": f"获取任务详情失败: {str(e)}"},
            status_code=500
        )

# 新增使用查询参数的任务详情获取路由 - 解决参数冲突问题
@app.get("/api/task_detail")
@Web(auth_required=False)
async def get_task_by_id(request: Request, task_id: int):
    """获取单个任务的详细信息（通过查询参数）- 推荐使用此方法避免参数冲突"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"通过查询参数请求获取任务详情: ID={task_id}")
    try:
        # 从请求状态中获取用户信息
        user_info = getattr(request.state, "user", None)
        user_id = user_info.get("user_id", "test_user") if user_info else "test_user"
        logger.debug(f"当前用户: {user_id}, 请求任务ID: {task_id}")
        
        # 使用位置参数传递task_id
        task = await task_service.get_task(int(task_id))
        
        # 检查返回结果
        if not task:
            logger.warning(f"找不到任务: ID={task_id}")
            return JSONResponse(
                {"error": f"找不到任务: {task_id}"},
                status_code=404
            )
        
        # 检查是否返回了错误信息
        if task.get("error"):
            logger.error(f"获取任务失败: {task.get('error')}")
            return JSONResponse(
                {"error": task.get("error")},
                status_code=500
            )
        
        # 将日期时间对象转换为字符串
        for date_field in ["created_at", "updated_at", "completed_at"]:
            if date_field in task and isinstance(task[date_field], datetime):
                task[date_field] = task[date_field].isoformat()
        
        # 处理日志内容
        if "logs" in task and isinstance(task["logs"], bytes):
            try:
                task["logs"] = task["logs"].decode("utf-8", errors="replace")
            except Exception as decode_error:
                logger.error(f"解码日志失败: {str(decode_error)}")
                task["logs"] = "日志内容无法解码"
        elif not task.get("logs"):
            task["logs"] = "暂无日志信息"
        
        # 确保文件列表存在
        if "files" not in task or not task["files"]:
            task["files"] = []
        
        # 处理文件列表中的时间戳
        if isinstance(task["files"], list):
            for file in task["files"]:
                if "created_at" in file and isinstance(file["created_at"], datetime):
                    file["created_at"] = file["created_at"].isoformat()
        
        logger.info(f"成功获取任务详情: ID={task_id}")
        return task
    except Exception as e:
        logger.error(f"获取任务详情失败，意外错误: {str(e)}", exc_info=True)
        return JSONResponse(
            {"error": f"获取任务详情失败: {str(e)}"},
            status_code=500
        )

@app.get("/{full_path:path}")
@Web(auth_required=False)  # 不需要认证 - 静态文件和前端页面公开访问
async def serve_frontend(request: Request, full_path: str):
    """提供前端页面，作为默认路由返回静态index.html文件"""
    # 排除API路径，避免覆盖特定API路由
    if full_path == "tasks" or full_path.startswith("tasks/"):
        raise HTTPException(status_code=404, detail="Not Found")
        
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    
    # 如果有静态HTML文件，直接返回
    if full_path.strip() == "" or full_path == "index.html":
        # 检查app/static目录下是否有index.html
        static_index_path = STATIC_DIR / "index.html"
        if static_index_path.exists():
            return FileResponse(static_index_path, headers=headers)
        
        # 使用静态HTML文件
        if INDEX_HTML_PATH.exists():
            return FileResponse(INDEX_HTML_PATH, headers=headers)
        else:
            # 如果静态文件不存在，动态生成
            # 定义样式表和JS脚本
            css_files = [
                "/static/css/styles.css",
                "/static/css/login.css"
            ]
            
            js_files = [
                "/static/js/auth.js?v=1.0.1",
                "/static/js/login.js?v=1.0.0",
                "/static/js/main.js?v=1.0.1"
            ]
            
            # 生成HTML
            html_content = '<!DOCTYPE html>\n'
            html_content += '<html lang="zh-CN">\n'
            html_content += '<head>\n'
            html_content += '    <meta charset="UTF-8">\n'
            html_content += '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            html_content += '    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">\n'
            html_content += '    <meta http-equiv="Pragma" content="no-cache">\n'
            html_content += '    <meta http-equiv="Expires" content="0">\n'
            html_content += '    <title>OpenManus - 智能AI代码生成器</title>\n'
            
            # 添加CSS样式
            for css_file in css_files:
                html_content += f'    <link rel="stylesheet" href="{css_file}?v={uuid.uuid4().hex[:8]}">\n'
            
            # 添加外部CSS
            html_content += '    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.2.0/github-markdown.min.css">\n'
            html_content += '</head>\n'
            html_content += '<body>\n'
            html_content += '    <style id="override-styles">\n'
            html_content += '        /* 直接在body中添加样式覆盖，确保最高优先级 */\n'
            html_content += '        .log-entry, \n'
            html_content += '        .log-entry::before,\n'
            html_content += '        .log-entry * {\n'
            html_content += '            background-color: white !important;\n'
            html_content += '            border-left: none !important;\n'
            html_content += '            border-left-width: 0 !important;\n'
            html_content += '            border-left-color: transparent !important;\n'
            html_content += '        }\n'
            html_content += '        .log-entry::before {\n'
            html_content += '            content: none !important;\n'
            html_content += '            display: none !important;\n'
            html_content += '        }\n'
            html_content += '        /* 移除所有绿色边框 */\n'
            html_content += '        * {\n'
            html_content += '            border-left-color: transparent !important;\n'
            html_content += '        }\n'
            html_content += '    </style>\n'
            html_content += '    <header class="header">\n'
            html_content += '        <h1>OpenManus</h1>\n'
            html_content += '        <!-- 认证状态将由login.js动态添加 -->\n'
            html_content += '    </header>\n\n'
            html_content += '    <div class="main-container">\n'
            html_content += '        <!-- 输入面板 -->\n'
            html_content += '        <div class="input-panel">\n'
            html_content += '            <h2 class="panel-header">任务设置</h2>\n'
            html_content += '            <div class="input-container">\n'
            html_content += '                <textarea id="prompt" placeholder="请输入您想要完成的任务描述..."></textarea>\n'
            html_content += '                <button id="submit">执行任务</button>\n'
            html_content += '                <div id="processing-indicator" class="processing-indicator">处理中，请稍候...</div>\n'
            html_content += '            </div>\n'
            html_content += '        </div>\n\n'
            html_content += '        <!-- 日志/文件面板 -->\n'
            html_content += '        <div class="log-panel">\n'
            html_content += '            <div class="tab-container">\n'
            html_content += '                <div class="tab active" data-target="logs-tab">执行日志</div>\n'
            html_content += '                <div class="tab" data-target="files-tab">生成文件</div>\n'
            html_content += '            </div>\n'
            html_content += '            \n'
            html_content += '            <!-- 日志内容 -->\n'
            html_content += '            <div id="logs-tab" class="tab-content active">\n'
            html_content += '                <div id="logs" class="logs-container markdown-body"></div>\n'
            html_content += '            </div>\n'
            html_content += '            \n'
            html_content += '            <!-- 文件内容 -->\n'
            html_content += '            <div id="files-tab" class="tab-content">\n'
            html_content += '                <div id="files" class="files-container">\n'
            html_content += '                    <div id="no-files-message" class="no-files-message">暂无生成文件</div>\n'
            html_content += '                </div>\n'
            html_content += '            </div>\n'
            html_content += '        </div>\n'
            html_content += '    </div>\n\n'
            
            # 添加JS脚本
            for js_file in js_files:
                html_content += f'    <script src="{js_file}?v={uuid.uuid4().hex[:8]}"></script>\n'
            
            html_content += '</body>\n'
            html_content += '</html>\n'
            
            return HTMLResponse(content=html_content, headers=headers)
    
    return Response(status_code=404)

@app.get("/favicon.ico")
@Web(auth_required=False)  # 不需要认证 - 网站图标公开访问
async def favicon(request: Request):
    """处理favicon请求"""
    # 检查是否存在favicon文件
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    else:
        # 返回空响应
        return Response(status_code=204)

# 修改process端点，使用装饰器进行认证
@app.post('/api/process')
@Web()  # 默认需要认证
async def process_prompt(request: Request):
    """处理用户的提示，需要认证"""
    form = await request.form()
    prompt = form.get('prompt', '')
    
    # 从配置中获取默认模型
    from app.config import config
    default_model = config.llm["default"].model
    model = form.get('model', default_model)
    
    if not prompt:
        return JSONResponse({'error': '请提供任务描述'}, status_code=400)
    
    # 从请求状态中获取用户信息（由认证装饰器添加）
    user_info = getattr(request.state, "user", None)
    
    # 异步处理任务
    asyncio.create_task(process_prompt_with_agent(prompt, model, user_info))
    
    return JSONResponse({'status': 'processing'})

@app.get("/api/test")
@Web(auth_required=False)
async def test_api(request: Request):
    """测试API端点"""
    return {"status": "ok", "message": "API系统正常工作"}

# 添加测试任务列表接口
@app.get("/api/tasks/test")
@Web(auth_required=False)
async def test_tasks(request: Request):
    """测试任务列表接口"""
    return [
        {"id": 1, "name": "测试任务1", "status": "completed", "created_at": "2023-01-01"},
        {"id": 2, "name": "测试任务2", "status": "pending", "created_at": "2023-01-02"}
    ]

# 直接添加任务列表API而不通过router
@app.get("/api/tasks-direct")
@Web(auth_required=False)
async def get_tasks_direct(request: Request):
    """直接从任务服务获取任务列表（包括内存和数据库中的任务）"""
    try:
        # 从请求状态中获取用户信息
        user_info = getattr(request.state, "user", None)
        user_id = user_info.get("user_id", "test_user") if user_info else "test_user"
            
        # 使用任务服务获取所有任务
        tasks = await task_service.get_user_tasks(user_id, 20, 0)
        
        # 将日期时间对象转换为字符串
        for task in tasks:
            if "created_at" in task and isinstance(task["created_at"], datetime):
                task["created_at"] = task["created_at"].isoformat()
            if "updated_at" in task and isinstance(task["updated_at"], datetime):
                task["updated_at"] = task["updated_at"].isoformat()
            if "completed_at" in task and isinstance(task["completed_at"], datetime):
                task["completed_at"] = task["completed_at"].isoformat()
        
        return tasks
    except Exception as e:
        return JSONResponse(
            {"error": f"无法获取任务列表: {str(e)}"},
            status_code=500
        )

# 添加任务服务诊断端点
@app.get("/api/debug/task-service")
@Web(auth_required=False)
async def debug_task_service(request: Request):
    """诊断任务服务的状态"""
    from app.services.task_service import task_service
    try:
        # 检查服务实例
        service_info = {
            "instance_exists": task_service is not None,
            "type": str(type(task_service)),
        }
        
        # 检查数据库连接
        db_info = {
            "db_available": getattr(task_service, "db_available", False),
        }
        
        # 尝试简单操作
        try:
            tasks = await task_service.get_user_tasks("test_user", 5, 0)
            operation_info = {
                "get_tasks_success": True,
                "tasks_count": len(tasks) if tasks else 0,
                "tasks": tasks
            }
        except Exception as e:
            operation_info = {
                "get_tasks_success": False,
                "error": str(e)
            }
            
        return {
            "service": service_info,
            "database": db_info,
            "operation": operation_info
        }
    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

# 添加一个调试端点来显示所有注册的路由
@app.get("/api/debug/routes")
@Web(auth_required=False)
async def debug_routes(request: Request):
    """显示所有注册的路由信息"""
    routes = []
    for route in app.routes:
        route_info = {
            "path": getattr(route, "path", str(route)),
            "name": getattr(route, "name", None),
            "endpoint": getattr(route, "endpoint", None).__name__ if hasattr(getattr(route, "endpoint", None), "__name__") else str(getattr(route, "endpoint", None)),
            "methods": list(getattr(route, "methods", [])) if hasattr(route, "methods") else None,
        }
        routes.append(route_info)
    
    # 尝试获取task_router的路由信息
    task_routes = []
    try:
        for route in task_router.routes:
            route_info = {
                "path": getattr(route, "path", str(route)),
                "name": getattr(route, "name", None),
                "endpoint": getattr(route, "endpoint", None).__name__ if hasattr(getattr(route, "endpoint", None), "__name__") else str(getattr(route, "endpoint", None)),
                "methods": list(getattr(route, "methods", [])) if hasattr(route, "methods") else None
            }
            task_routes.append(route_info)
    except Exception as e:
        task_routes = [{"error": str(e)}]
    
    # 返回所有路由信息
    return {
        "all_routes": routes,
        "task_router_routes": task_routes,
        "task_router_prefix": getattr(task_router, "prefix", None)
    }

@app.get("/tasks")
@Web(auth_required=False)
async def redirect_to_api_tasks(request: Request):
    """将/tasks路径重定向到/api/tasks"""
    return RedirectResponse(url="/api/tasks") 

# 新增使用查询参数的任务文件获取路由 - 配合task_detail端点
@app.get("/api/task_detail/files")
@Web(auth_required=False)
async def get_task_files_by_id(request: Request):
    """获取任务的文件列表（通过查询参数）- 配合task_detail端点使用"""
    import logging
    logger = logging.getLogger(__name__)
    
    # 从查询参数中获取task_id
    task_id = request.query_params.get('task_id')
    if not task_id:
        return JSONResponse(
            status_code=400,
            content={"error": "缺少任务ID参数"}
        )
    
    logger.info(f"通过查询参数请求获取任务文件: ID={task_id}")
    try:
        # 从请求状态中获取用户信息
        user_info = getattr(request.state, "user", None)
        user_id = user_info.get("user_id", "test_user") if user_info else "test_user"
        logger.debug(f"当前用户: {user_id}, 请求任务文件ID: {task_id}")
        
        # 确保任务存在
        task = await task_service.get_task(int(task_id))
        if not task:
            logger.warning(f"任务不存在: ID={task_id}")
            return JSONResponse(
                {"error": f"找不到任务: {task_id}"},
                status_code=404
            )
        
        # 直接调用获取文件的方法，避免通过task获取
        files = await task_service.get_task_files(int(task_id))
        logger.debug(f"获取到文件列表: {files}")
        
        if files is None:
            logger.warning(f"找不到任务文件: ID={task_id}")
            return JSONResponse(
                {"error": f"找不到任务文件: {task_id}"},
                status_code=404
            )
            
        # 确保文件列表不为None
        files = files or []
        
        # 将日期时间对象转换为字符串
        for file in files:
            if "created_at" in file and isinstance(file["created_at"], datetime):
                file["created_at"] = file["created_at"].isoformat()
        
        logger.info(f"成功获取任务文件列表: ID={task_id}, 文件数量={len(files)}")
        return files
    except Exception as e:
        logger.error(f"获取任务文件列表失败，意外错误: {str(e)}", exc_info=True)
        return JSONResponse(
            {"error": f"获取任务文件列表失败: {str(e)}"},
            status_code=500
        )

@app.post("/api/task_detail/logs")
@Web(auth_required=False)  # 暂时不要求认证，方便测试
async def get_task_logs(request: Request):
    """
    根据任务ID获取任务日志
    参数:
    - task_id: 任务ID (从请求体中获取)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 记录用户信息和请求
    user_info = get_user_info(request)
    logger.info(f"访问任务日志API: 用户={user_info.get('username', '未知')}")
    
    try:
        # 解析请求体
        request_data = await request.json()
        logger.debug(f"请求体数据: {request_data}")
    except Exception as e:
        logger.error(f"解析请求体失败: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"error": "无效的请求格式", "detail": str(e)}
        )
    
    # 从请求体中获取task_id
    task_id = request_data.get("task_id")
    if not task_id:
        logger.warning("缺少task_id参数")
        return JSONResponse(
            status_code=400,
            content={"error": "缺少task_id参数"}
        )
    
    # 记录日志查询信息
    logger.info(f"获取任务日志: task_id={task_id}")
    
    # 验证任务是否存在
    task = await task_service.get_task_by_id(task_id)
    if not task:
        logger.warning(f"任务不存在: task_id={task_id}")
        return JSONResponse(
            status_code=404,
            content={"error": f"任务不存在: {task_id}"}
        )
    
    # 获取任务日志
    try:
        logs = await task_service.get_task_logs(task_id)
        
        # 格式化日期时间为ISO格式
        if logs and isinstance(logs, list):
            for log in logs:
                if "timestamp" in log and log["timestamp"]:
                    if isinstance(log["timestamp"], datetime):
                        log["timestamp"] = log["timestamp"].isoformat()
        
        logger.info(f"成功获取任务日志: task_id={task_id}, 日志数量={len(logs) if logs else 0}")
        return {"logs": logs or []}
    except Exception as e:
        logger.error(f"获取任务日志失败: task_id={task_id}, 错误: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"获取任务日志失败: {str(e)}"}
        )

# 新增使用请求体参数的任务文件获取路由 - 配合task_detail端点
@app.post("/api/task_detail/files")
@Web(auth_required=False)
async def get_task_files_by_id(request: Request):
    """获取任务的文件列表（通过请求体）- 配合task_detail端点使用"""
    import logging
    logger = logging.getLogger(__name__)
    
    # 从请求体中获取task_id
    try:
        body = await request.json()
        task_id = body.get('task_id')
    except Exception as e:
        logger.error(f"解析请求体出错: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"error": "无效的请求体格式，需要JSON格式"}
        )
    
    if not task_id:
        return JSONResponse(
            status_code=400,
            content={"error": "缺少任务ID参数"}
        )
    
    logger.info(f"通过请求体请求获取任务文件: ID={task_id}")
    try:
        # 从请求状态中获取用户信息
        user_info = getattr(request.state, "user", None)
        user_id = user_info.get("user_id", "test_user") if user_info else "test_user"
        logger.debug(f"当前用户: {user_id}, 请求任务文件ID: {task_id}")
        
        # 确保任务存在
        task = await task_service.get_task(int(task_id))
        if not task:
            logger.warning(f"任务不存在: ID={task_id}")
            return JSONResponse(
                {"error": f"找不到任务: {task_id}"},
                status_code=404
            )
        
        # 直接调用获取文件的方法，避免通过task获取
        files = await task_service.get_task_files(int(task_id))
        logger.debug(f"获取到文件列表: {files}")
        
        if files is None:
            logger.warning(f"找不到任务文件: ID={task_id}")
            return JSONResponse(
                {"error": f"找不到任务文件: {task_id}"},
                status_code=404
            )
            
        # 确保文件列表不为None
        files = files or []
        
        # 将日期时间对象转换为字符串
        for file in files:
            if "created_at" in file and isinstance(file["created_at"], datetime):
                file["created_at"] = file["created_at"].isoformat()
        
        logger.info(f"成功获取任务文件列表: ID={task_id}, 文件数量={len(files)}")
        return files
    except Exception as e:
        logger.error(f"获取任务文件列表失败，意外错误: {str(e)}", exc_info=True)
        return JSONResponse(
            {"error": f"获取任务文件列表失败: {str(e)}"},
            status_code=500
        )

@app.get("/api/run")
@Web()  # 默认需要认证
async def run_task(request: Request, prompt: str):
    """处理用户输入的提示并返回事件流"""
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream"
    }
    
    # 启动任务处理
    asyncio.create_task(handle_prompt({"prompt": prompt}))
    
    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers=headers
    )