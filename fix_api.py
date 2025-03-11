"""
修复OpenManus API问题的辅助脚本

这个脚本用于修复以下问题：
1. OpenAI API密钥和base_url配置问题
2. 文件生成识别机制问题

使用方法：运行 python fix_api.py
"""

import re
import os
import toml
import shutil
from pathlib import Path

def main():
    print("开始修复OpenManus API配置和文件识别问题...")
    
    # 1. 备份原始文件
    api_path = Path("app/api.py")
    backup_path = Path("app/api.py.bak")
    
    if not api_path.exists():
        print(f"错误：找不到文件 {api_path}")
        return
    
    # 创建备份
    shutil.copy2(api_path, backup_path)
    print(f"已创建备份文件：{backup_path}")
    
    # 2. 读取原始文件内容
    with open(api_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 3. 修复OpenAI API配置
    openai_config_pattern = re.compile(
        r"# 读取配置文件\ntry:.*?openai_api_key = \"\"\n    openai_model = \"gpt-3\.5-turbo\"",
        re.DOTALL
    )
    
    new_openai_config = """# 读取配置文件
try:
    config = toml.load("config/config.toml")
    openai_api_key = config.get("llm", {}).get("api_key", "")
    openai_model = config.get("llm", {}).get("model", "gpt-4o")
    openai_base_url = config.get("llm", {}).get("base_url", "")
    
    # 设置OpenAI客户端配置
    if openai_api_key:
        if openai_base_url:
            # 如果有自定义base_url，则同时设置base_url和api_key
            print(f"使用自定义API基础URL: {openai_base_url}")
            # 使用新的客户端方式
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
    else:
        client = None
except Exception as e:
    print(f"读取配置文件失败: {str(e)}")
    openai_api_key = ""
    openai_model = "gpt-3.5-turbo"
    openai_base_url = ""
    client = None"""
    
    if openai_config_pattern.search(content):
        content = openai_config_pattern.sub(new_openai_config, content)
        print("已更新OpenAI API配置")
    else:
        print("警告：无法找到OpenAI配置部分，请手动更新")
    
    # 4. 修复generate_task_summary函数
    task_summary_pattern = re.compile(
        r"async def generate_task_summary\(prompt, logs\):.*?return last_task_summary",
        re.DOTALL
    )
    
    new_task_summary = """async def generate_task_summary(prompt, logs):
    """使用OpenAI API生成任务执行结果的摘要"""
    global summary_generation_status, last_task_summary, client
    
    try:
        # 更新摘要生成状态
        summary_generation_status = {
            "in_progress": True,
            "message": "正在生成任务摘要..."
        }
        
        # 如果没有配置API密钥，则返回提示信息
        if not openai_api_key or client is None:
            last_task_summary = "无法生成详细摘要：未配置OpenAI API密钥或客户端初始化失败。请在config/config.toml中配置。"
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
            {"role": "user", "content": f\"""请分析以下任务执行日志，并简洁地总结以下内容：
1. 任务的主要目标是什么
2. 任务是否成功完成
3. 生成了哪些文件及其主要内容和用途
4. 有没有遇到明显的错误或问题

请用中文回答，简明扼要，不超过300字。

任务提示: {prompt}

执行日志:
{logs_text[:50000]}  # 限制日志长度，防止超出token限制
\"""}
        ]
        
        # 重试机制
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 使用客户端调用OpenAI API
                print(f"使用模型 {openai_model} 生成摘要，重试次数: {retry_count}")
                
                # 使用客户端发送请求
                response = client.chat.completions.create(
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
        return last_task_summary"""
    
    if task_summary_pattern.search(content):
        content = task_summary_pattern.sub(new_task_summary, content)
        print("已更新generate_task_summary函数")
    else:
        print("警告：无法找到generate_task_summary函数，请手动更新")
    
    # 5. 添加AI文件识别功能
    identify_files_pattern = re.compile(
        r"def identify_generated_files\(prompt\):.*?return generated_files",
        re.DOTALL
    )
    
    new_identify_files = """def identify_generated_files(prompt):
    """从日志中识别生成的文件"""
    global generated_files, current_task_logs, client
    generated_files = []
    
    # 记录日志
    print(f"开始识别生成的文件，日志行数: {len(current_task_logs)}")
    
    # 将日志合并为一个字符串
    logs_text = "\n".join(current_task_logs)
    
    # 方法1：使用正则表达式匹配常见的文件路径
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
    
    # 方法2：如果配置了API密钥，使用AI识别文件
    if not file_paths and client is not None and openai_api_key:
        try:
            print("正在使用AI识别生成的文件...")
            
            # 构建提示信息，让AI帮助识别生成的文件
            messages = [
                {"role": "system", "content": "你是一个专门识别文件信息的助手。你的任务是从日志文本中提取明确提到的生成或修改的文件路径。只返回确实存在的文件路径，格式为JSON数组。"},
                {"role": "user", "content": f\"""请从以下日志中识别所有生成或修改的文件路径。只返回一个JSON数组，其中包含所有文件路径。例如: ["file1.txt", "path/to/file2.csv"]
                
任务提示: {prompt}

日志内容:
{logs_text[:20000]}  # 限制日志长度
\"""}
            ]
            
            # 调用API
            response = client.chat.completions.create(
                model=openai_model,
                messages=messages,
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            # 解析结果
            if response.choices and len(response.choices) > 0:
                import json
                try:
                    content = response.choices[0].message.content
                    result = json.loads(content)
                    
                    if "files" in result and isinstance(result["files"], list):
                        ai_files = result["files"]
                    elif isinstance(result, list):
                        ai_files = result
                    else:
                        ai_files = []
                        # 尝试查找回答中的所有字符串并检查它们是否为文件
                        for key, value in result.items():
                            if isinstance(value, list):
                                ai_files.extend(value)
                            elif isinstance(value, str):
                                ai_files.append(value)
                    
                    # 验证文件是否存在
                    for file_path in ai_files:
                        if os.path.isfile(file_path):
                            file_paths.add(file_path)
                            
                    print(f"AI识别到 {len(file_paths)} 个文件")
                except json.JSONDecodeError:
                    print("解析AI响应时出错，无法识别文件")
        except Exception as e:
            print(f"使用AI识别文件时出错: {str(e)}")
    
    # 如果没有找到文件，尝试在项目目录下查找最近修改的文件
    if not file_paths:
        print("未找到文件，尝试查找最近修改的文件")
        current_time = time.time()
        # 查找项目目录下最近1分钟内创建或修改的文件
        for root, _, files in os.walk("."):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    # 跳过常见的不相关文件
                    if file.startswith(".") or "__pycache__" in file_path:
                        continue
                        
                    # 检查文件修改时间
                    file_mtime = os.path.getmtime(file_path)
                    if current_time - file_mtime < 60:  # 1分钟内修改的文件
                        file_paths.add(file_path)
                except Exception:
                    pass
    
    # 构建生成文件的信息
    for file_path in file_paths:
        try:
            # 计算文件大小
            file_size = os.path.getsize(file_path)
            size_str = f"{file_size} B"
            if file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            
            # 尝试判断文件类型
            ext = os.path.splitext(file_path)[1].lower()
            file_type = "未知"
            if ext in [".txt", ".md", ".log"]:
                file_type = "文本文件"
            elif ext in [".csv", ".xlsx", ".xls"]:
                file_type = "数据表格"
            elif ext in [".docx", ".doc", ".pdf", ".pptx", ".ppt"]:
                file_type = "文档"
            elif ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"]:
                file_type = "图片"
            elif ext in [".py", ".js", ".html", ".css", ".c", ".cpp", ".java"]:
                file_type = "代码文件"
            
            # 添加到生成文件列表
            generated_files.append({
                "path": file_path,
                "name": os.path.basename(file_path),
                "size": size_str,
                "type": file_type,
                "mtime": os.path.getmtime(file_path)
            })
        except Exception as e:
            print(f"处理文件 {file_path} 时出错: {str(e)}")
    
    print(f"已识别到 {len(generated_files)} 个生成的文件")
    return generated_files"""
    
    if identify_files_pattern.search(content):
        content = identify_files_pattern.sub(new_identify_files, content)
        print("已更新identify_generated_files函数")
    else:
        print("警告：无法找到identify_generated_files函数，请手动更新")
    
    # 6. 保存修改后的文件
    with open(api_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"已成功更新文件 {api_path}")
    print("请重启应用以应用更改")

if __name__ == "__main__":
    main() 