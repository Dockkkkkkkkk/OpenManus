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
from starlette.responses import Response, FileResponse
import uuid
import toml
import openai
import sys
import random
import traceback
from datetime import datetime, timedelta
import platform
try:
    from ai_file_identifier import AIFileIdentifier
except ImportError:
    print("注意: AI文件识别器模块未找到，将使用传统方法识别文件")
    pass

app = FastAPI()

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

# 读取配置文件
try:
    config = toml.load("config/config.toml")
    openai_api_key = config.get("llm", {}).get("api_key", "")
    openai_model = config.get("llm", {}).get("model", "gpt-4o")
    openai_base_url = config.get("llm", {}).get("base_url", "")
    
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

# 添加异步处理提示的函数
async def process_prompt_with_agent(agent, prompt):
    """使用智能体处理用户提示词
    
    Args:
        agent: 智能体实例
        prompt: 用户提示词
    
    Returns:
        生成的文件列表
    """
    global generated_files, current_task_logs, pure_logs, logs_processor_callback
    
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
    
    try:
        # 记录输入的提示
        print(f"执行任务: {prompt}")
        
        # 添加日志拦截处理
        def logs_processor(message):
            # 清理日志内容
            cleaned_log = message  # 日志已在log_interceptor中清理过
            
            # 添加到纯净日志
            if cleaned_log:
                pure_logs.append(cleaned_log)
                
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
                segment_files = await identify_generated_files(segment_text, prompt=prompt)
                if segment_files:
                    print(f"第 {segment_num} 段识别到 {len(segment_files)} 个文件")
                    for file in segment_files:
                        if file not in generated_files:
                            generated_files.append(file)
                            print(f"添加新文件: {file}")
                            
                            # 发送文件通知给前端
                            message_queue.put_nowait({
                                "content": f"识别到新文件: {file}",
                                "file": file
                            })
                else:
                    print(f"第 {segment_num} 段未识别到文件")
            except Exception as e:
                print(f"处理第 {segment_num} 段时出错: {str(e)}")
        
        # 设置全局回调
        logs_processor_callback = logs_processor
        
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
            final_files = await identify_generated_files(all_logs, prompt=prompt)
            for file in final_files:
                if file not in generated_files:
                    generated_files.append(file)
                    # 发送文件通知给前端
                    message_queue.put_nowait({
                        "content": f"识别到新文件: {file}",
                        "file": file
                    })
        
        # 清除回调
        logs_processor_callback = None
        
        # 发送完成标记
        log_interceptor("处理完成")
        
        # 返回生成的文件列表
        return {"files": generated_files}
    except Exception as e:
        error_msg = f"处理任务时出错: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        
        # 发送错误消息
        log_interceptor(error_msg)
        
        # 即使出错也尝试发送完成标记
        log_interceptor("处理完成")
        
        return {"error": error_msg}

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
    """下载指定的文件（路径参数版本）"""
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

@app.get("/api/download")
async def download_file_query(filename: str):
    """下载指定的文件（查询参数版本）"""
    # 查找匹配的文件
    matching_files = []
    for f in generated_files:
        if isinstance(f, str):
            if os.path.basename(f) == filename:
                matching_files.append(f)
        elif isinstance(f, dict) and f.get("name") == filename:
            matching_files.append(f.get("path"))
    
    if not matching_files:
        raise HTTPException(status_code=404, detail=f"文件未找到: {filename}")
    
    file_path = matching_files[0]
    
    # 返回文件
    return FileResponse(
        path=file_path, 
        filename=filename,
        media_type="application/octet-stream"
    )

@app.get("/api/history")
async def get_history():
    """获取对话历史记录"""
    return {"history": conversation_history}

# 挂载静态文件目录
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/api/run")
async def run_task(prompt: str):
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

@app.get("/{full_path:path}")
async def serve_frontend(request: Request, full_path: str):
    """提供前端页面，作为默认路由返回静态index.html文件"""
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    
    if full_path.strip() == "" or full_path == "index.html":
        # 使用静态HTML文件
        if INDEX_HTML_PATH.exists():
            return FileResponse(INDEX_HTML_PATH, headers=headers)
        else:
            return Response(content=f"前端文件不存在: {INDEX_HTML_PATH}", status_code=404)
    
    return Response(status_code=404) 