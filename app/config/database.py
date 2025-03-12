"""
数据库配置模块
包含MySQL数据库和对象存储(COS)的相关配置项
"""
import os
import logging

# 设置日志
logger = logging.getLogger(__name__)

# MySQL数据库配置
class DatabaseConfig:
    # 安全地获取整数环境变量
    @staticmethod
    def _get_int_env(name, fallback_name=None, default="3306"):
        value = os.environ.get(name, os.environ.get(fallback_name, default) if fallback_name else default)
        
        # 尝试转换为整数
        try:
            # 确保值只包含数字
            if isinstance(value, str):
                # 处理可能的注释和引号
                if '#' in value:
                    value = value.split('#', 1)[0]
                value = value.strip().strip("'\"")
            return int(value)
        except (ValueError, TypeError) as e:
            logger.error(f"环境变量 {name} 值 '{value}' 无法转换为整数，使用默认值 {default}。错误: {e}")
            return int(default)
    
    HOST = os.environ.get("DB_HOST", os.environ.get("MYSQL_HOST", "localhost"))
    PORT = _get_int_env.__func__("DB_PORT", "MYSQL_PORT", "3306")
    USER = os.environ.get("DB_USER", os.environ.get("MYSQL_USER", "root"))
    PASSWORD = os.environ.get("DB_PASSWORD", os.environ.get("MYSQL_PASSWORD", "password"))
    DATABASE = os.environ.get("DB_NAME", os.environ.get("MYSQL_DATABASE", "openmanus"))
    CHARSET = "utf8mb4"
    
    @classmethod
    def get_connection_params(cls):
        """获取数据库连接参数"""
        return {
            "host": cls.HOST,
            "port": cls.PORT,
            "user": cls.USER,
            "password": cls.PASSWORD,
            "database": cls.DATABASE,
            "charset": cls.CHARSET
        }
    
    @classmethod
    def get_connection_string(cls):
        """获取数据库连接字符串"""
        return f"mysql+pymysql://{cls.USER}:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{cls.DATABASE}"

# 腾讯云对象存储(COS)配置
class COSConfig:
    SECRET_ID = os.environ.get("COS_SECRET_ID", "")
    SECRET_KEY = os.environ.get("COS_SECRET_KEY", "")
    REGION = os.environ.get("COS_REGION", "ap-nanjing")
    BUCKET = os.environ.get("COS_BUCKET", "")
    URL_PREFIX = os.environ.get("COS_URL_PREFIX", "")
    
    @classmethod
    def is_configured(cls):
        """检查COS配置是否完整"""
        return all([cls.SECRET_ID, cls.SECRET_KEY, cls.REGION, cls.BUCKET])
    
    @classmethod
    def get_url_prefix(cls):
        """获取COS URL前缀"""
        if cls.URL_PREFIX:
            return cls.URL_PREFIX
        elif cls.BUCKET and cls.REGION:
            return f"https://{cls.BUCKET}.cos.{cls.REGION}.myqcloud.com"
        return ""

# 数据库表结构配置
class DatabaseSchema:
    # 任务表名
    TASKS_TABLE = "tasks"
    
    # 文件表名
    FILES_TABLE = "files"
    
    # 任务状态枚举
    TASK_STATUS = {
        "PENDING": "pending",
        "RUNNING": "running",
        "COMPLETED": "completed",
        "FAILED": "failed"
    } 