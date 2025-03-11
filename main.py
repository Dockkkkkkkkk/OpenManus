import asyncio
import threading
import uvicorn
import platform
import sys
from app.agent.manus import Manus
from app.logger import logger
from app.api import app, log_interceptor, message_queue

# 创建一个全局变量存储最新的用户输入
user_input_queue = asyncio.Queue()

# 修改API处理函数，将用户输入放入队列
async def api_handle_prompt(prompt):
    await user_input_queue.put(prompt)
    return {"status": "success", "message": "命令已提交"}

# 覆盖API模块中的处理函数
@app.post("/api/prompt")
async def handle_prompt(prompt: dict):
    return await api_handle_prompt(prompt.get("prompt", ""))

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
    """异步运行Manus代理"""
    logger.info("正在等待用户输入...")
    
    agent = Manus()
    
    while True:
        try:
            # 尝试从队列获取输入
            prompt = None
            
            try:
                # 使用一个短暂的超时，允许检查控制台输入
                prompt = await asyncio.wait_for(user_input_queue.get(), timeout=0.1)
                logger.info(f"从Web界面接收到提示: {prompt}")
            except asyncio.TimeoutError:
                # 如果队列中没有数据，尝试从控制台读取
                if asyncio.get_event_loop().is_running():
                    # 根据平台选择合适的输入检测方法
                    input_available = False
                    if platform.system() == 'Windows':
                        input_available = check_input_windows()
                    else:
                        # Unix/Linux/Mac
                        if sys.stdin.isatty() and hasattr(sys.stdin, 'fileno'):
                            input_available = check_input_unix()
                    
                    if input_available:
                        prompt = input("Enter your prompt (or 'exit' to quit): ")
            
            if prompt is None:
                # 如果没有输入，继续等待
                await asyncio.sleep(0.1)
                continue
                
            if prompt.lower() == "exit":
                logger.info("Goodbye!")
                break
                
            logger.warning("Processing your request...")
            await agent.run(prompt)
            
        except KeyboardInterrupt:
            logger.warning("Goodbye!")
            break

async def main():
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

if __name__ == "__main__":
    asyncio.run(main())
