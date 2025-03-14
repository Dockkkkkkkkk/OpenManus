import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import pymysql
from pymysql.cursors import DictCursor
from fastapi import HTTPException
import traceback

# 导入配置
from app.config.database import DatabaseConfig, DatabaseSchema

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DBService:
    """数据库服务，提供任务和文件的CRUD操作"""
    
    def __init__(self):
        self.db_available = False  # 默认数据库不可用
        try:
            self.init_db()
            # 如果初始化成功，设置标志为可用
            self.db_available = True
            logger.info("数据库服务初始化成功")
        except Exception as e:
            logger.error(f"数据库服务初始化失败: {str(e)}")
            logger.error(traceback.format_exc())
            logger.warning("将在无数据库模式下运行，部分功能可能不可用")
    
    def get_connection(self):
        """获取数据库连接"""
        if not self.db_available:
            logger.warning("数据库不可用，无法获取连接")
            raise HTTPException(status_code=503, detail="数据库服务不可用")
            
        try:
            # 获取连接参数
            params = DatabaseConfig.get_connection_params()
            
            # 处理cursorclass参数
            if params.get('cursorclass') == 'DictCursor':
                params['cursorclass'] = DictCursor
            
            # 记录连接尝试（不含密码）
            conn_info = {k: v for k, v in params.items() if k != 'password'}
            logger.debug(f"尝试连接数据库: {conn_info}")
            
            # 使用干净的连接参数
            conn = pymysql.connect(
                **params,
                connect_timeout=10,  # 设置连接超时
                client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,  # 启用多语句支持
                conv=pymysql.converters.conversions,  # 使用默认转换器
                autocommit=True  # 自动提交
            )
            logger.debug("数据库连接成功")
            return conn
        except UnicodeEncodeError as ue:
            logger.error(f"数据库连接编码错误: {str(ue)}")
            logger.error(traceback.format_exc())
            self.db_available = False
            raise HTTPException(status_code=500, detail=f"数据库编码错误: {str(ue)}")
        except Exception as e:
            logger.error(f"数据库连接失败: {str(e)}")
            logger.error(traceback.format_exc())
            self.db_available = False  # 连接失败时更新状态
            raise
    
    def init_db(self):
        """初始化数据库，创建表结构"""
        logger.info(f"初始化MySQL数据库: {DatabaseConfig.HOST}:{DatabaseConfig.PORT}/{DatabaseConfig.DATABASE}")
        
        try:
            # 确保数据库存在
            self._ensure_database_exists()
            
            # 读取SQL文件
            sql_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "create_tables.sql")
            
            if os.path.exists(sql_file_path):
                with open(sql_file_path, 'r', encoding='utf-8') as f:
                    sql_script = f.read()
                
                # 连接数据库
                conn = self.get_connection()
                try:
                    cursor = conn.cursor()
                    
                    # 分割SQL语句并执行
                    statements = sql_script.split(';')
                    for statement in statements:
                        statement = statement.strip()
                        if statement:  # 确保不执行空语句
                            try:
                                cursor.execute(statement)
                            except Exception as stmt_err:
                                logger.warning(f"执行SQL语句失败: {str(stmt_err)}")
                                # 继续执行其他语句
                    
                    conn.commit()
                    logger.info("数据库表创建完成")
                except Exception as cursor_err:
                    logger.error(f"执行SQL失败: {str(cursor_err)}")
                    conn.rollback()
                finally:
                    conn.close()
            else:
                # 如果SQL文件不存在，尝试手动创建表
                logger.warning(f"SQL文件不存在: {sql_file_path}, 尝试手动创建表")
                self._init_tables_manually()
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
            # 不重新抛出异常，允许程序继续运行，只是可能数据库功能不可用
            pass
    
    def _ensure_database_exists(self):
        """确保数据库存在，如果不存在则创建"""
        try:
            # 获取数据库主机信息
            host = DatabaseConfig.HOST
            port = DatabaseConfig.PORT
            user = DatabaseConfig.USER
            
            # 构建不带数据库名的连接参数
            params = DatabaseConfig.get_connection_params()
            params.pop('database', None)  # 移除数据库名
            
            if 'init_command' in params:
                params.pop('init_command')  # 移除初始化命令
            
            logger.info(f"尝试连接数据库服务器: {host}:{port}, 用户: {user}")
            
            # 处理cursorclass参数
            if params.get('cursorclass') == 'DictCursor':
                params['cursorclass'] = DictCursor
            
            # 不指定数据库名连接到MySQL服务器
            conn = pymysql.connect(**params)
            
            try:
                database_name = DatabaseConfig.DATABASE
                with conn.cursor() as cursor:
                    # 检查数据库是否存在
                    cursor.execute(f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s", (database_name,))
                    result = cursor.fetchone()
                    
                    if not result:
                        # 创建数据库
                        cursor.execute(f"CREATE DATABASE {database_name} DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci")
                        logger.info(f"创建数据库成功: {database_name}")
                    else:
                        logger.info(f"数据库已存在: {database_name}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"检查/创建数据库失败: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _init_tables_manually(self):
        """手动创建表结构（备用方案）"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # 创建任务表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INT PRIMARY KEY AUTO_INCREMENT COMMENT '任务ID，主键',
                user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
                prompt VARCHAR(2000) NOT NULL COMMENT '提示词内容',
                status VARCHAR(20) NOT NULL COMMENT '任务状态: pending, running, completed, failed',
                log_url VARCHAR(512) COMMENT '日志文件COS存储URL',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                completed_at TIMESTAMP NULL COMMENT '完成时间'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务记录表'
            ''')
            
            # 创建文件表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INT PRIMARY KEY AUTO_INCREMENT COMMENT '文件ID，主键',
                task_id INT NOT NULL COMMENT '关联的任务ID',
                filename VARCHAR(255) NOT NULL COMMENT '文件名',
                cos_url VARCHAR(512) NOT NULL COMMENT '腾讯云COS存储URL',
                content_type VARCHAR(128) COMMENT '文件MIME类型',
                file_size INT COMMENT '文件大小(字节)',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务生成文件表'
            ''')
            
            # 创建索引
            try:
                cursor.execute('CREATE INDEX idx_tasks_user_id ON tasks(user_id) COMMENT \'用户ID索引，加速按用户查询任务\'')
            except Exception as e:
                # 忽略索引已存在错误
                if not ('Duplicate' in str(e) or 'already exists' in str(e)):
                    logger.error(f"创建任务表用户ID索引失败: {str(e)}")
                    raise
            
            try:
                cursor.execute('CREATE INDEX idx_files_task_id ON files(task_id) COMMENT \'任务ID索引，加速查询任务关联的文件\'')
            except Exception as e:
                # 忽略索引已存在错误
                if not ('Duplicate' in str(e) or 'already exists' in str(e)):
                    logger.error(f"创建文件表任务ID索引失败: {str(e)}")
                    raise
            
            conn.commit()
            logger.info("手动初始化数据库完成")
        except Exception as e:
            conn.rollback()
            logger.error(f"手动初始化数据库失败: {str(e)}")
            raise
        finally:
            conn.close()

    # 以下方法需要调整为MySQL风格，主要是SQL语法的变化
    
    def create_task(self, user_id: str, prompt: str) -> int:
        """创建新任务"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute(
                'INSERT INTO tasks (user_id, prompt, status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)',
                (user_id, prompt, 'pending', now, now)
            )
            task_id = cursor.lastrowid
            conn.commit()
            return task_id
        except Exception as e:
            conn.rollback()
            logger.error(f"创建任务失败: {str(e)}")
            raise
        finally:
            conn.close()
    
    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """获取单个任务详情"""
        try:
            conn = self.get_connection()
            cursor = None
            
            try:
                cursor = conn.cursor()
                
                # 获取任务信息
                logger.info(f"正在从数据库获取任务: ID={task_id}")
                cursor.execute('SELECT * FROM tasks WHERE id = %s', (task_id,))
                task = cursor.fetchone()
                
                if not task:
                    logger.warning(f"未找到任务: ID={task_id}")
                    return None
                
                # 获取任务文件
                logger.info(f"正在获取任务文件: 任务ID={task_id}")
                cursor.execute('SELECT * FROM files WHERE task_id = %s', (task_id,))
                files = cursor.fetchall()
                
                # 将结果转换为字典
                if isinstance(task, dict):
                    task_dict = task
                else:
                    # 如果使用的不是DictCursor，手动转换
                    try:
                        task_dict = dict(task)
                    except Exception as e:
                        logger.error(f"无法将任务转换为字典: {str(e)}")
                        # 创建基本字典
                        field_names = [desc[0] for desc in cursor.description]
                        task_dict = dict(zip(field_names, task))
                
                # 处理文件
                if files:
                    if isinstance(files[0], dict):
                        task_dict['files'] = files
                    else:
                        # 手动转换文件列表
                        try:
                            cursor.execute('SHOW COLUMNS FROM files')
                            file_fields = [col[0] for col in cursor.fetchall()]
                            task_dict['files'] = [dict(zip(file_fields, file)) for file in files]
                        except Exception as e:
                            logger.error(f"无法转换文件列表: {str(e)}")
                            task_dict['files'] = []
                else:
                    task_dict['files'] = []
                
                logger.info(f"成功获取任务及其{len(task_dict.get('files', []))}个文件: ID={task_id}")
                return task_dict
            except Exception as e:
                logger.error(f"获取任务失败，数据库错误: {str(e)}")
                return {"id": task_id, "error": f"获取任务失败: {str(e)}", "status": "error", "files": []}
            finally:
                if cursor:
                    cursor.close()
                conn.close()
        except Exception as conn_err:
            logger.error(f"获取任务失败，连接错误: {str(conn_err)}")
            return {"id": task_id, "error": f"数据库连接失败: {str(conn_err)}", "status": "error", "files": []}
    
    def get_user_tasks(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """获取用户的任务列表"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # 获取任务基本信息和文件计数
            cursor.execute('''
                SELECT t.*, COUNT(f.id) as file_count
                FROM tasks t
                LEFT JOIN files f ON t.id = f.task_id
                WHERE t.user_id = %s
                GROUP BY t.id
                ORDER BY t.created_at DESC
                LIMIT %s OFFSET %s
            ''', (user_id, limit, offset))
            
            tasks = cursor.fetchall()
            return [dict(task) for task in tasks]
        except Exception as e:
            logger.error(f"获取用户任务列表失败: {str(e)}")
            raise
        finally:
            conn.close()
    
    def get_all_tasks(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """获取所有任务列表（管理员功能）"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # 获取任务基本信息和文件计数
            cursor.execute('''
                SELECT t.*, COUNT(f.id) as file_count
                FROM tasks t
                LEFT JOIN files f ON t.id = f.task_id
                GROUP BY t.id
                ORDER BY t.created_at DESC
                LIMIT %s OFFSET %s
            ''', (limit, offset))
            
            tasks = cursor.fetchall()
            return [dict(task) for task in tasks]
        except Exception as e:
            logger.error(f"获取所有任务列表失败: {str(e)}")
            raise
        finally:
            conn.close()
    
    def update_task_status(self, task_id: int, status: str, log_url: Optional[str] = None) -> bool:
        """更新任务状态和日志URL"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if status == 'completed' or status == 'failed':
                # 任务完成或失败时，设置完成时间
                if log_url is not None:
                    cursor.execute(
                        'UPDATE tasks SET status = %s, log_url = %s, updated_at = %s, completed_at = %s WHERE id = %s',
                        (status, log_url, now, now, task_id)
                    )
                else:
                    cursor.execute(
                        'UPDATE tasks SET status = %s, updated_at = %s, completed_at = %s WHERE id = %s',
                        (status, now, now, task_id)
                    )
            else:
                # 其他状态更新
                if log_url is not None:
                    cursor.execute(
                        'UPDATE tasks SET status = %s, log_url = %s, updated_at = %s WHERE id = %s',
                        (status, log_url, now, task_id)
                    )
                else:
                    cursor.execute(
                        'UPDATE tasks SET status = %s, updated_at = %s WHERE id = %s',
                        (status, now, task_id)
                    )
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"更新任务状态失败: {str(e)}")
            raise
        finally:
            conn.close()
    
    def update_task_log_url(self, task_id: int, log_url: str) -> bool:
        """更新任务日志URL"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 更新日志URL
            cursor.execute(
                'UPDATE tasks SET log_url = %s, updated_at = %s WHERE id = %s',
                (log_url, now, task_id)
            )
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"更新任务日志URL失败: {str(e)}")
            raise
        finally:
            conn.close()
    
    def update_task(self, task_id: int, update_data: Dict[str, Any]) -> bool:
        """更新任务的任意字段
        
        Args:
            task_id: 任务ID
            update_data: 要更新的字段及其值的字典，例如 {"status": "completed", "log_url": "http://..."}
            
        Returns:
            bool: 更新是否成功
        """
        if not update_data:
            return False
            
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 构建更新语句
            set_parts = []
            params = []
            
            # 添加更新字段
            for key, value in update_data.items():
                set_parts.append(f"{key} = %s")
                params.append(value)
                
            # 添加更新时间
            set_parts.append("updated_at = %s")
            params.append(now)
            
            # 添加任务ID
            params.append(task_id)
            
            # 执行更新
            query = f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = %s"
            logger.debug(f"执行更新任务: ID={task_id}, 查询={query}, 参数={params}")
            
            cursor.execute(query, params)
            conn.commit()
            
            success = cursor.rowcount > 0
            logger.info(f"更新任务成功: ID={task_id}, 受影响行数={cursor.rowcount}")
            return success
        except Exception as e:
            conn.rollback()
            logger.error(f"更新任务失败: ID={task_id}, 错误={str(e)}")
            raise
        finally:
            conn.close()
    
    def delete_task(self, task_id: int) -> bool:
        """删除任务及其关联文件"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # 删除任务（关联的文件会通过外键级联删除）
            cursor.execute('DELETE FROM tasks WHERE id = %s', (task_id,))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"删除任务失败: {str(e)}")
            raise
        finally:
            conn.close()
    
    # 文件相关操作
    
    def create_file(self, task_id: int, filename: str, cos_url: str, content_type: Optional[str] = None, file_size: Optional[int] = None) -> int:
        """创建文件记录"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute(
                'INSERT INTO files (task_id, filename, cos_url, content_type, file_size, created_at) VALUES (%s, %s, %s, %s, %s, %s)',
                (task_id, filename, cos_url, content_type, file_size, now)
            )
            file_id = cursor.lastrowid
            conn.commit()
            return file_id
        except Exception as e:
            conn.rollback()
            logger.error(f"创建文件记录失败: {str(e)}")
            raise
        finally:
            conn.close()
    
    def add_file(self, task_id: int, filename: str, file_url: str, content_type: str = "") -> int:
        """添加文件记录到数据库"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"添加文件记录: 任务ID={task_id}, 文件名={filename}")
            
            cursor.execute(
                'INSERT INTO files (task_id, filename, cos_url, content_type, created_at) VALUES (%s, %s, %s, %s, %s)',
                (task_id, filename, file_url, content_type, now)
            )
            file_id = cursor.lastrowid
            conn.commit()
            
            logger.info(f"文件记录添加成功: ID={file_id}")
            return file_id
        except Exception as e:
            conn.rollback()
            logger.error(f"添加文件记录失败: {str(e)}")
            raise  # 改为抛出异常，便于调用方处理错误
        finally:
            conn.close()
    
    def get_file(self, file_id: int) -> Optional[Dict[str, Any]]:
        """获取单个文件的详细信息"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = f"""
                    SELECT * 
                    FROM {DatabaseSchema.FILES_TABLE}
                    WHERE id = %s
                    """
                    cursor.execute(query, (file_id,))
                    file = cursor.fetchone()
                    return file
        except Exception as e:
            logger.error(f"获取文件详情失败: {str(e)}")
            return None
    
    def get_task_files(self, task_id: int) -> List[Dict[str, Any]]:
        """获取任务的所有文件"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = f"""
                    SELECT * 
                    FROM {DatabaseSchema.FILES_TABLE}
                    WHERE task_id = %s
                    ORDER BY created_at DESC
                    """
                    cursor.execute(query, (task_id,))
                    files = cursor.fetchall()
                    return files
        except Exception as e:
            logger.error(f"获取任务文件失败: {str(e)}")
            return []
    
    def delete_file(self, file_id: int) -> bool:
        """删除文件记录"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM files WHERE id = %s', (file_id,))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"删除文件记录失败: {str(e)}")
            raise
        finally:
            conn.close()

# 创建单例实例
db_service = DBService() 