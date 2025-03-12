"""
数据库配置模块
包含MySQL数据库和对象存储(COS)的相关配置项
"""
import os
import logging
import base64

# 设置日志
logger = logging.getLogger(__name__)

# 默认数据库配置
DEFAULT_DB_CONFIG = {
    "HOST": "localhost",
    "PORT": 3306,
    "USER": "root",
    "PASSWORD": "password",
    "DATABASE": "openmanus",
    "CHARSET": "utf8mb4"
}

# MySQL数据库配置
class DatabaseConfig:
    # 安全地获取整数环境变量
    @staticmethod
    def _get_int_env(name, fallback_name=None, default=3306):
        """获取整数类型的环境变量"""
        value = os.environ.get(name, os.environ.get(fallback_name, str(default)) if fallback_name else str(default))
        
        # 尝试转换为整数
        try:
            # 确保值只包含数字
            if isinstance(value, str):
                # 移除注释和引号
                if '#' in value:
                    value = value.split('#', 1)[0]
                value = value.strip().strip("'\"")
            return int(value)
        except (ValueError, TypeError) as e:
            logger.error(f"环境变量 {name} 值 '{value}' 无法转换为整数，使用默认值 {default}。错误: {e}")
            return int(default)
    
    # 安全地获取字符串环境变量
    @staticmethod
    def _get_str_env(name, fallback_name=None, default=""):
        """获取字符串类型的环境变量，处理注释和引号"""
        value = os.environ.get(name, os.environ.get(fallback_name, default) if fallback_name else default)
        
        # 处理可能的注释和引号
        if isinstance(value, str):
            if '#' in value:
                value = value.split('#', 1)[0]
            value = value.strip().strip("'\"")
        
        return value
    
    # 读取环境变量或使用默认值
    HOST = _get_str_env.__func__("DB_HOST", "MYSQL_HOST", DEFAULT_DB_CONFIG["HOST"])
    PORT = _get_int_env.__func__("DB_PORT", "MYSQL_PORT", DEFAULT_DB_CONFIG["PORT"])
    USER = _get_str_env.__func__("DB_USER", "MYSQL_USER", DEFAULT_DB_CONFIG["USER"])
    # 获取原始密码
    _RAW_PASSWORD = _get_str_env.__func__("DB_PASSWORD", "MYSQL_PASSWORD", DEFAULT_DB_CONFIG["PASSWORD"])
    # 处理密码以避免编码问题
    PASSWORD = _RAW_PASSWORD
    DATABASE = _get_str_env.__func__("DB_NAME", "MYSQL_DATABASE", DEFAULT_DB_CONFIG["DATABASE"])
    CHARSET = DEFAULT_DB_CONFIG["CHARSET"]  # 使用utf8mb4编码支持完整的Unicode字符集，包括Emoji和中文
    
    @classmethod
    def get_connection_params(cls):
        """获取数据库连接参数"""
        # 处理密码中的非ASCII字符
        password = cls._RAW_PASSWORD
        
        # 检查密码是否含有非ASCII字符
        has_non_ascii = False
        try:
            password.encode('ascii')  # 尝试编码为ASCII
        except UnicodeEncodeError:
            has_non_ascii = True
        
        if has_non_ascii:
            logger.warning("数据库密码包含非ASCII字符，将使用默认安全密码")
            password = DEFAULT_DB_CONFIG["PASSWORD"]
        
        # 构建连接参数
        conn_params = {
            "host": cls.HOST,
            "port": cls.PORT,
            "user": cls.USER,
            "password": password,
            "database": cls.DATABASE,
            "charset": cls.CHARSET,
            "use_unicode": True,
            "init_command": "SET NAMES utf8mb4",
            "cursorclass": "DictCursor"  # 指定为字符串，避免直接引用对象
        }
        
        # 记录连接参数(排除密码)
        log_params = conn_params.copy()
        log_params["password"] = "******"
        logger.debug(f"数据库连接参数: {log_params}")
        
        return conn_params
    
    @classmethod
    def get_connection_string(cls):
        """获取数据库连接字符串"""
        return f"mysql+pymysql://{cls.USER}:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{cls.DATABASE}?charset={cls.CHARSET}"

# 腾讯云对象存储(COS)配置
class COSConfig:
    SECRET_ID = os.environ.get("COS_SECRET_ID", "")
    SECRET_KEY = os.environ.get("COS_SECRET_KEY", "")
    REGION = os.environ.get("COS_REGION", "ap-nanjing")
    _RAW_BUCKET = os.environ.get("COS_BUCKET", "video-cut-1320088203")
    
    # 确保存储桶名称符合规范（只允许字母、数字和连字符）
    BUCKET = "".join(c for c in _RAW_BUCKET if c.isalnum() or c == '-')
    
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