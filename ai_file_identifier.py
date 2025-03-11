"""
AI文件识别器模块

该模块提供基于AI语义分析的文件识别功能，通过分析任务执行日志
识别出在任务执行过程中生成或修改的文件。
"""

import os
import re
import json
import time
import asyncio
from typing import List, Dict, Set, Any, Optional
from datetime import datetime, timedelta
import traceback

# 导入OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("OpenAI模块导入失败，AI文件识别将不可用")

class AIFileIdentifier:
    """基于AI的文件识别器，用于从日志中识别生成的文件"""
    
    def __init__(self):
        """初始化AI文件识别器
        
        读取环境变量或配置文件中的API密钥和模型信息
        """
        # 导入配置
        try:
            import tomli
            with open("config/config.toml", "rb") as f:
                config = tomli.load(f)
                
            # 读取OpenAI配置
            openai_config = config.get("openai", {})
            self.api_key = openai_config.get("api_key", "")
            self.api_base = openai_config.get("api_base", "")
            self.model = openai_config.get("model", "gpt-3.5-turbo")
            
            # 如果OpenAI配置为空，尝试使用LLM配置
            if not self.api_key and "llm" in config:
                llm_config = config.get("llm", {})
                self.api_key = llm_config.get("api_key", "")
                self.api_base = llm_config.get("base_url", "")
                self.model = llm_config.get("model", "gpt-3.5-turbo")
                print("使用LLM配置初始化OpenAI客户端")
            
            # 初始化OpenAI客户端
            if OPENAI_AVAILABLE and self.api_key:
                print(f"正在初始化OpenAI客户端，API基础URL: {self.api_base}")
                client_params = {
                    "api_key": self.api_key,
                }
                
                # 设置基础URL（如果存在）
                if self.api_base:
                    client_params["base_url"] = self.api_base
                
                # 创建客户端
                self.client = OpenAI(**client_params)
                print("OpenAI客户端初始化成功")
            else:
                self.client = None
                print("OpenAI客户端初始化失败，AI文件识别不可用")
                
        except Exception as e:
            print(f"加载配置文件失败: {str(e)}")
            traceback.print_exc()
            self.client = None
            self.api_key = ""
            self.api_base = ""
            self.model = "gpt-3.5-turbo"
            
        # 初始化文件识别用的正则表达式
        self.file_patterns = [
            r"(?:保存|创建|生成|写入|saved|created|generated|written)(?:[了到至])?\s*(?:文件|file)?[：:]*\s*(?:为|as|to)?[：:]*\s*(?P<filepath>[\w\-./\\]+\.\w+)",
            r"(?:文件|file)\s*(?:已)?(?:成功)?(?:保存|创建|生成|写入|saved|created|generated|written)(?:[了到至])?[：:]*\s*(?:为|as|to)?[：:]*\s*(?P<filepath>[\w\-./\\]+\.\w+)",
            r"(?P<filepath>[\w\-./\\]+\.\w+)\s*(?:文件)?(?:已)?(?:成功)?(?:保存|创建|生成|写入|saved|created|generated|written)",
            r"Content successfully saved to (?P<filepath>[\w\-./\\]+\.\w+)",
            r"Successfully (?:saved|created|generated|written) (?:to|as|into) (?P<filepath>[\w\-./\\]+\.\w+)",
            r"(?P<filepath>[\w\-./\\]+\.\w+)"  # 最宽松的匹配，作为最后的尝试
        ]
    
    async def identify_files(self, prompt, logs):
        """使用AI分析日志，识别生成的文件
        
        同时使用AI和正则表达式识别日志中的文件，返回两者结果的并集
        
        Args:
            prompt: 用户提示，提供上下文
            logs: 执行日志
            
        Returns:
            生成的文件路径列表
        """
        all_files = set()  # 使用集合自动去重
        
        # 首先尝试使用AI识别
        if self.client and self.api_key:
            try:
                print("开始使用AI识别文件...")
                ai_files = await self._ai_identification(prompt, logs)
                if ai_files:
                    print(f"AI成功识别出 {len(ai_files)} 个文件")
                    for file in ai_files:
                        if os.path.exists(file):
                            all_files.add(file)
            except Exception as e:
                print(f"AI文件识别失败: {str(e)}")
                traceback.print_exc()
        else:
            print("OpenAI客户端不可用")
        
        # 同时使用正则表达式识别
        if isinstance(logs, list):
            logs_text = "\n".join(logs)
        else:
            logs_text = logs
            
        regex_files = self._regex_identification(logs_text)
        print(f"正则表达式识别出 {len(regex_files)} 个文件")
        for file in regex_files:
            if os.path.exists(file):
                all_files.add(file)
        
        # 转换集合为列表
        result = list(all_files)
        print(f"总共识别到 {len(result)} 个文件")
        return result
    
    async def _ai_identification(self, prompt, logs):
        """使用AI分析日志识别生成的文件
        
        构建提示，让AI从日志中提取生成的文件路径
        
        Args:
            prompt: 用户提示
            logs: 执行日志
            
        Returns:
            识别出的文件路径列表
        """
        # 构建提示
        if isinstance(logs, list):
            logs_text = "\n".join(logs[-200:])  # 仅使用最后200行日志，避免超出上下文限制
        else:
            logs_text = logs[-10000:]  # 如果已经是字符串，取最后10000个字符
        
        messages = [
            {"role": "system", "content": "你是一个精确的日志分析专家，专门从执行日志中提取生成的文件路径。请只返回文件路径，每行一个，不要添加任何解释。如果没有找到任何文件，返回'NO_FILES_FOUND'。"},
            {"role": "user", "content": f"以下是一个任务的执行日志，用户请求是：{prompt}\n\n请从日志中提取所有生成或保存的文件路径，按照生成顺序列出。只返回文件路径，每行一个，不要添加任何解释。\n\n日志内容:\n{logs_text}"}
        ]
        
        try:
            print(f"向AI发送请求，分析日志中的文件路径...")
            # 异步调用OpenAI API
            response = await asyncio.to_thread(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=1000
                )
            )
            
            # 处理响应
            content = response.choices[0].message.content.strip()
            print(f"AI响应: {content[:100]}...")
            
            # 如果没有找到文件
            if content == "NO_FILES_FOUND":
                print("AI未找到任何文件")
                return []
            
            # 解析文件路径，每行一个
            file_paths = [line.strip() for line in content.split("\n") if line.strip()]
            print(f"从AI响应中解析出 {len(file_paths)} 个文件路径")
            
            # 验证文件路径
            valid_files = []
            for path in file_paths:
                # 去除可能的引号和空格
                clean_path = path.strip().strip('"\'')
                
                # 检查文件是否存在
                if os.path.exists(clean_path):
                    valid_files.append(clean_path)
                    print(f"验证文件存在: {clean_path}")
                elif os.path.exists(os.path.join(os.getcwd(), clean_path)):
                    valid_files.append(clean_path)
                    print(f"验证文件存在(相对路径): {clean_path}")
                else:
                    print(f"文件不存在: {clean_path}")
            
            print(f"AI识别出 {len(valid_files)} 个有效文件")
            return valid_files
            
        except Exception as e:
            print(f"AI文件识别请求失败: {str(e)}")
            traceback.print_exc()
            return []
    
    def _regex_identification(self, logs):
        """使用正则表达式从日志中识别文件路径
        
        Args:
            logs: 执行日志内容
            
        Returns:
            识别出的文件路径列表
        """
        found_files = []
        
        for pattern in self.file_patterns:
            try:
                matches = re.finditer(pattern, logs)
                for match in matches:
                    try:
                        filepath = match.group('filepath').strip().strip('"\'')
                        # 验证文件是否存在
                        if os.path.exists(filepath):
                            # 排除一些系统文件和临时文件
                            if not (filepath.startswith(".") or 
                                   filepath.endswith(".pyc") or 
                                   "__pycache__" in filepath or
                                   "FETCH_HEAD" in filepath):
                                if filepath not in found_files:
                                    found_files.append(filepath)
                    except Exception as e:
                        print(f"处理正则匹配结果失败: {str(e)}")
            except Exception as e:
                print(f"正则匹配处理错误: {str(e)}")
        
        print(f"正则表达式识别到 {len(found_files)} 个文件")
        return found_files 