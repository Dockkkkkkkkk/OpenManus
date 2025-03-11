"""
修复OpenManus中的OpenAI API调用问题

该脚本修复两个主要问题：
1. OpenAI API 404错误 - 由于API端点或版本不匹配导致
2. 流式响应处理 - 确保正确设置流式请求并处理响应

使用方法: python fix_openai_api.py
"""

import re
import os
import toml
import shutil
import json
from pathlib import Path

def main():
    print("开始修复OpenManus中的OpenAI API调用问题...")
    
    # 1. 备份原始文件
    api_path = Path("app/api.py")
    backup_path = Path("app/api.py.bak")
    
    if not api_path.exists():
        print(f"错误：找不到文件 {api_path}")
        return
    
    # 创建备份
    if not backup_path.exists():
        shutil.copy2(api_path, backup_path)
        print(f"已创建备份文件：{backup_path}")
    else:
        print(f"备份文件已存在：{backup_path}")
    
    # 2. 读取原始文件内容
    with open(api_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 3. 修复OpenAI API配置
    openai_config_pattern = re.compile(
        r"# 读取配置文件\ntry:.*?client = None",
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
    \"\"\"使用OpenAI API生成任务执行结果的摘要\"\"\"
    global summary_generation_status, last_task_summary, client
    
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
            
        logs_text = "\\n".join(logs)
        print(f"开始为任务生成摘要，日志长度：{len(logs_text)}")
        
        # 构建提示信息
        messages = [
            {"role": "system", "content": "你是一个任务执行分析专家，需要分析执行日志并提供简洁的总结。"},
            {"role": "user", "content": f\"\"\"请分析以下任务执行日志，并简洁地总结以下内容：
1. 任务的主要目标是什么
2. 任务是否成功完成
3. 生成了哪些文件及其主要内容和用途
4. 有没有遇到明显的错误或问题

请用中文回答，简明扼要，不超过300字。

任务提示: {prompt}

执行日志:
{logs_text[:50000]}  # 限制日志长度，防止超出token限制
\"\"\"}
        ]
        
        # 重试机制
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                print(f"正在调用OpenAI API (重试 {retry_count}/{max_retries})...")
                
                # 尝试使用不同的方法调用API
                if client:
                    # 方法1: 使用新版客户端，非流式
                    try:
                        print("使用新版客户端API...")
                        response = await asyncio.to_thread(
                            lambda: client.chat.completions.create(
                                model=openai_model,
                                messages=messages,
                                temperature=0.2,
                                max_tokens=500
                            )
                        )
                        
                        if response.choices and len(response.choices) > 0:
                            last_task_summary = response.choices[0].message.content
                            print("成功生成任务摘要")
                            break
                    except Exception as e1:
                        print(f"新版客户端API调用失败: {str(e1)}")
                        
                        # 方法2: 使用新版客户端，流式请求
                        try:
                            print("尝试使用流式请求...")
                            stream_response = await asyncio.to_thread(
                                lambda: client.chat.completions.create(
                                    model=openai_model,
                                    messages=messages,
                                    temperature=0.2,
                                    max_tokens=500,
                                    stream=True
                                )
                            )
                            
                            # 处理流式响应
                            full_response = ""
                            for chunk in stream_response:
                                if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                                    content = chunk.choices[0].delta.content
                                    if content:
                                        full_response += content
                            
                            if full_response:
                                last_task_summary = full_response
                                print("成功生成任务摘要(流式)")
                                break
                        except Exception as e2:
                            print(f"流式请求失败: {str(e2)}")
                
                # 方法3: 使用旧版API接口（兼容模式）
                try:
                    print("尝试使用兼容模式...")
                    if not 'api_base' in dir(openai) and openai_base_url:
                        openai.api_base = openai_base_url
                    
                    response = await asyncio.to_thread(
                        lambda: openai.ChatCompletion.create(
                            model=openai_model,
                            messages=messages,
                            temperature=0.2,
                            max_tokens=500
                        )
                    )
                    
                    if response.choices and len(response.choices) > 0:
                        last_task_summary = response.choices[0].message.content
                        print("成功生成任务摘要(兼容模式)")
                        break
                except Exception as e3:
                    print(f"兼容模式失败: {str(e3)}")
                
                # 方法4：使用直接HTTP请求（最后的尝试）
                try:
                    import httpx
                    print("尝试使用直接HTTP请求...")
                    
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {openai_api_key}"
                    }
                    
                    url = f"{openai_base_url if openai_base_url else 'https://api.openai.com'}/v1/chat/completions"
                    
                    payload = {
                        "model": openai_model,
                        "messages": messages,
                        "temperature": 0.2,
                        "max_tokens": 500
                    }
                    
                    async with httpx.AsyncClient() as http_client:
                        response = await http_client.post(
                            url,
                            headers=headers,
                            json=payload,
                            timeout=30.0
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            if "choices" in result and len(result["choices"]) > 0:
                                last_task_summary = result["choices"][0]["message"]["content"]
                                print("成功生成任务摘要(HTTP请求)")
                                break
                        else:
                            print(f"HTTP请求失败: {response.status_code} {response.text}")
                except Exception as e4:
                    print(f"HTTP请求出错: {str(e4)}")
                
                # 如果所有方法都失败，增加重试计数
                retry_count += 1
                await asyncio.sleep(2)  # 等待2秒后重试
                
            except Exception as e:
                error_message = f"重试 {retry_count+1}/{max_retries} 失败: {str(e)}"
                print(error_message)
                retry_count += 1
                await asyncio.sleep(2)  # 出错后等待2秒
        
        # 如果所有重试都失败
        if retry_count >= max_retries and not last_task_summary:
            last_task_summary = "无法生成详细摘要：连接API服务器失败，请检查网络或API配置。"
            print("所有重试尝试均失败")
            
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
    
    # 5. 保存修改后的文件
    with open(api_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"已成功更新文件 {api_path}")
    print("请重启应用以应用更改")

if __name__ == "__main__":
    main() 