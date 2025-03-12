import asyncio
import threading
import uvicorn
import platform
import sys
import os
from pathlib import Path
from app.agent.manus import Manus
from app.logger import logger
from app.api import app, log_interceptor, message_queue

# 创建一个全局变量存储最新的用户输入
user_input_queue = asyncio.Queue()
# 添加一个标志变量，用于标记队列中是否有数据
has_new_input = False

# 修改API处理函数，将用户输入放入队列
async def api_handle_prompt(prompt):
    print(f"api_handle_prompt函数被调用，参数: {prompt}")
    try:
        print("准备将提示放入队列")
        global has_new_input
        await user_input_queue.put(prompt)
        has_new_input = True  # 设置标志，表示有新数据
        print("提示已成功放入队列，has_new_input设置为True")
        # 确保请求被正确处理
        return {"status": "success", "message": "命令已提交"}
    except Exception as e:
        print(f"api_handle_prompt函数出错: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise

# 注释掉这个函数，因为它与app/api.py中的函数冲突
# @app.post("/api/prompt")
# async def handle_prompt(prompt: dict):
#     return await api_handle_prompt(prompt.get("prompt", ""))

# 自定义日志处理方法，将日志消息发送到log_interceptor
def log_handler(message):
    # Loguru消息格式化
    record = message.record
    log_level = record["level"].name
    log_msg = record["message"]
    formatted_message = f"{log_level} | {log_msg}"
    log_interceptor(formatted_message)

# 添加自定义日志处理器
logger.add(log_handler)

# 检查Windows平台上的控制台输入
def check_input_windows():
    try:
        import msvcrt
        return msvcrt.kbhit()  # 返回True如果有按键等待处理
    except ImportError:
        return False

# 检查Unix/Linux/Mac平台上的控制台输入
def check_input_unix():
    import select
    return select.select([sys.stdin], [], [], 0)[0]

async def manus_task():
    """后台任务，处理用户输入并执行Manus代理"""
    logger.info("正在等待用户输入...")
    log_interceptor("Manus代理初始化成功，已准备好接收指令")
    
    # 初始化Manus代理
    try:
        agent = Manus()
        logger.info("Manus代理初始化成功")
    except Exception as e:
        logger.error(f"Manus代理初始化失败: {str(e)}")
        log_interceptor(f"Manus代理初始化失败: {str(e)}")
        return
    
    # 主处理循环
    while True:
        try:
            # 声明全局变量
            global has_new_input
            
            prompt = None
            # 1. 优先检查前端输入队列
            if has_new_input:
                try:
                    print("检测到新输入，从队列获取...")
                    # 从队列获取数据
                    prompt = user_input_queue.get_nowait()
                    has_new_input = False  # 重置标志
                    print(f"从队列获取到提示: {prompt}")
                    if prompt:
                        logger.info(f"从前端接收到提示: {prompt}")
                        log_interceptor(f"INFO | 从前端接收到提示: {prompt}")
                except asyncio.QueueEmpty:
                    print("队列为空，重置标志")
                    has_new_input = False
            else:
                # 检查控制台输入
                # 根据操作系统选择合适的控制台输入检查方法
                if platform.system() == "Windows":
                    prompt = check_input_windows()
                else:
                    prompt = check_input_unix()
                
                # 如果有控制台输入
                if prompt:
                    logger.info(f"从控制台接收到提示: {prompt}")
                    log_interceptor(f"INFO | 从控制台接收到提示: {prompt}")
                    # 将控制台输入添加到队列中，以便前端能够看到
                    log_interceptor(f"用户: {prompt}")
            
            # 如果没有输入，继续下一次循环
            if not prompt:
                await asyncio.sleep(0.5)  # 增加休眠时间，减少CPU使用率
                continue
                
            # 处理输入
            print(f"开始处理提示: {prompt}")
            warning_msg = f"正在处理您的请求: {prompt}"
            logger.warning(warning_msg)
            log_interceptor(warning_msg)
            
            # 执行Manus代理
            try:
                # 运行代理并获取结果
                result = await agent.run(prompt)
                
                # 处理结果 - 如果结果很长，按行分割发送
                logger.info("处理完成，结果如下:")
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
                logger.error(error_msg)
                # 向前端发送简化的错误消息
                log_interceptor(f"执行错误: {str(e)}")
                log_interceptor("处理完成")
                
        except Exception as e:
            # 捕获主循环中的所有异常
            logger.exception(f"处理输入时发生错误: {str(e)}")
            log_interceptor(f"系统错误: {str(e)}")
            await asyncio.sleep(1)  # 出错后短暂暂停

# 检查并构建前端
def build_frontend_if_needed():
    root_dir = Path(__file__).parent
    static_dir = root_dir / "static" / "frontend"
    
    # 如果静态目录不存在或为空，尝试构建前端
    if not static_dir.exists() or not any(static_dir.iterdir()):
        logger.info("前端静态文件不存在，尝试构建...")
        try:
            # 检查是否存在构建脚本
            build_script = root_dir / "build_frontend.py"
            if build_script.exists():
                # 如果存在构建脚本，执行它
                import subprocess
                result = subprocess.run([sys.executable, str(build_script)], capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("前端构建成功！")
                    logger.debug(result.stdout)
                else:
                    logger.warning("前端构建失败！将使用内置的基本界面")
                    logger.debug(f"错误: {result.stderr}")
            else:
                logger.warning("找不到前端构建脚本，将使用内置的基本界面")
        except Exception as e:
            logger.error(f"构建前端时出错: {e}")

# 检查并初始化环境
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
    if not index_path.exists():
        print(f"已创建文件：{index_path}")
    else:
        print(f"文件已存在：{index_path}")

async def main():
    # 初始化环境
    init_environment()
    
    # 检查并构建前端
    build_frontend_if_needed()
    
    # 启动Manus代理
    asyncio.create_task(manus_task())
    
    # 启动API服务器（内置前端）
    config = uvicorn.Config(
        app=app, 
        host="0.0.0.0", 
        port=8000, 
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

# 主入口
if __name__ == "__main__":
    # 显示数据库配置
    from app.config.database import DatabaseConfig
    print("\n数据库配置信息:")
    print(f"主机: {DatabaseConfig.HOST}")
    print(f"端口: {DatabaseConfig.PORT}")
    print(f"用户: {DatabaseConfig.USER}")
    print(f"数据库: {DatabaseConfig.DATABASE}")
    print(f"字符集: {DatabaseConfig.CHARSET}")
    print("-" * 40)
    
    # 启动应用
    asyncio.run(main())
