"""配置模块

包含应用程序各项配置，如数据库连接、对象存储等
"""

import pathlib
import os
import logging
from dotenv import load_dotenv
import sys

# 设置日志
logger = logging.getLogger(__name__)

# 定义项目根目录
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent.absolute()

# 环境变量文件路径
ENV_PATH = PROJECT_ROOT / '.env'

# 加载环境变量
try:
    # 尝试使用python-dotenv加载环境变量，自动处理编码问题
    # 如果存在.env文件则加载，不存在则跳过
    logger.info(f"尝试从 {ENV_PATH} 加载环境变量")
    # 使用verbose=True可以输出加载的变量信息
    load_success = load_dotenv(dotenv_path=ENV_PATH, verbose=True, encoding='utf-8')
    
    if load_success:
        logger.info("成功加载.env文件")
    else:
        logger.warning(f".env文件不存在或为空: {ENV_PATH}，将使用默认配置运行")
        # 设置一些基本的默认环境变量，确保应用可以启动
        default_vars = {
            "DB_HOST": "localhost",
            "DB_PORT": "3306",
            "DB_USER": "root",
            "DB_PASSWORD": "",
            "DB_NAME": "openmanus"
        }
        for key, value in default_vars.items():
            if key not in os.environ:
                os.environ[key] = value
                logger.debug(f"已设置默认环境变量: {key}={value}")
except Exception as e:
    logger.error(f"加载.env文件时出错: {str(e)}，将使用默认配置运行")
    # 如果load_dotenv失败，确保设置默认变量
    default_vars = {
        "DB_HOST": "localhost",
        "DB_PORT": "3306",
        "DB_USER": "root",
        "DB_PASSWORD": "",
        "DB_NAME": "openmanus"
    }
    for key, value in default_vars.items():
        if key not in os.environ:
            os.environ[key] = value
            logger.debug(f"已设置默认环境变量: {key}={value}")

# 导入配置类，方便直接从config模块引入
from app.config.database import DatabaseConfig, COSConfig, DatabaseSchema
from app.config.settings import LLMSettings

# 解决LLM配置问题 - 确保app.config.llm可以被访问
# 注: 由于app/llm.py会导入app.config模块并使用其llm属性，
# 我们需要引入根模块中的config实例
import importlib.util
spec = importlib.util.spec_from_file_location("root_config", os.path.join(PROJECT_ROOT, "app", "config.py"))
root_config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(root_config_module)
config = root_config_module.config
logger.info("已从根目录导入config实例")

# 配置版本
__version__ = "1.0.0"