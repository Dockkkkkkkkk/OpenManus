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
    # 导入初始化模块
    try:
        import init_env
        init_env.init_environment()
    except Exception as e:
        print(f"初始化环境时出错: {e}")
        # 创建基本目录结构
        try:
            static_dir = Path(__file__).parent / "static"
            frontend_dir = static_dir / "frontend"
            static_dir.mkdir(exist_ok=True)
            frontend_dir.mkdir(exist_ok=True)
        except Exception as inner_e:
            print(f"创建目录失败: {inner_e}")

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

if __name__ == "__main__":
    asyncio.run(main())
