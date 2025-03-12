import os
import logging
import glob
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import tempfile
import io
import uuid

from app.services.db_service import db_service
from app.services.cos_service import cos_service

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaskService:
    """任务管理服务，整合数据库操作和文件处理"""
    
    def __init__(self):
        # 内存存储，作为数据库不可用时的备选
        self.in_memory_tasks = {}
        self.in_memory_files = {}
        self.in_memory_logs = {}
    
    async def create_task(self, user_id: str, prompt: str) -> int:
        """创建新任务"""
        try:
            if not db_service.db_available:
                # 如果数据库不可用，使用内存存储
                task_id = str(uuid.uuid4())
                self.in_memory_tasks[task_id] = {
                    "id": task_id,
                    "user_id": user_id,
                    "prompt": prompt,
                    "status": "pending",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                logger.info(f"内存模式: 创建任务成功: ID={task_id}, 用户={user_id}")
                return task_id
                
            # 创建任务记录
            task_id = db_service.create_task(user_id, prompt)
            logger.info(f"创建任务成功: ID={task_id}, 用户={user_id}")
            return task_id
        except Exception as e:
            logger.error(f"创建任务失败: {str(e)}")
            # 使用内存存储作为备选
            task_id = str(uuid.uuid4())
            self.in_memory_tasks[task_id] = {
                "id": task_id,
                "user_id": user_id,
                "prompt": prompt,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            logger.info(f"内存模式(备选): 创建任务成功: ID={task_id}, 用户={user_id}")
            return task_id
    
    async def get_task(self, task_id: int) -> Dict:
        """获取任务信息"""
        try:
            if not db_service.db_available:
                # 如果数据库不可用，从内存中获取任务
                if str(task_id) in self.in_memory_tasks:
                    task = self.in_memory_tasks[str(task_id)]
                    # 添加日志信息
                    if str(task_id) in self.in_memory_logs:
                        task["logs"] = self.in_memory_logs[str(task_id)]
                    else:
                        task["logs"] = ""
                    # 添加文件信息
                    if str(task_id) in self.in_memory_files:
                        task["files"] = self.in_memory_files[str(task_id)]
                    else:
                        task["files"] = []
                    logger.debug(f"内存模式: 获取任务: ID={task_id}")
                    return task
                else:
                    logger.warning(f"内存模式: 获取任务失败: 找不到任务 ID={task_id}")
                    return {}
                    
            # 使用数据库服务获取任务信息
            task = db_service.get_task(task_id)
            if not task:
                logger.warning(f"获取任务失败: 找不到任务 ID={task_id}")
                return {}
                
            # 获取任务日志
            if task.get('log_url'):
                try:
                    logs = await cos_service.download_file(task['log_url'])
                    task['logs'] = logs
                except Exception as e:
                    logger.error(f"获取任务日志失败: {str(e)}")
                    task['logs'] = ""
            else:
                task['logs'] = ""
                
            # 获取任务文件
            task['files'] = db_service.get_task_files(task_id)
            
            return task
        except Exception as e:
            logger.error(f"获取任务信息失败: {str(e)}")
            # 尝试从内存中获取
            if str(task_id) in self.in_memory_tasks:
                task = self.in_memory_tasks[str(task_id)]
                if str(task_id) in self.in_memory_logs:
                    task["logs"] = self.in_memory_logs[str(task_id)]
                else:
                    task["logs"] = ""
                if str(task_id) in self.in_memory_files:
                    task["files"] = self.in_memory_files[str(task_id)]
                else:
                    task["files"] = []
                logger.debug(f"内存模式(备选): 获取任务: ID={task_id}")
                return task
            return {}
            
    async def get_user_tasks(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict]:
        """获取用户的所有任务，支持分页"""
        try:
            tasks = []
            
            if not db_service.db_available:
                # 如果数据库不可用，从内存中获取用户任务
                memory_tasks = []
                for task_id, task in self.in_memory_tasks.items():
                    if task.get("user_id") == user_id:
                        task_copy = task.copy()
                        if task_id in self.in_memory_logs:
                            task_copy["logs"] = self.in_memory_logs[task_id]
                        else:
                            task_copy["logs"] = ""
                        if task_id in self.in_memory_files:
                            task_copy["files"] = self.in_memory_files[task_id]
                        else:
                            task_copy["files"] = []
                        memory_tasks.append(task_copy)
                
                # 手动处理分页
                sorted_tasks = sorted(memory_tasks, key=lambda x: x.get("created_at", ""), reverse=True)
                page_tasks = sorted_tasks[offset:offset + limit]
                logger.debug(f"内存模式: 获取用户任务: 用户ID={user_id}, 任务数={len(page_tasks)}, 总数={len(sorted_tasks)}")
                return page_tasks
                
            # 使用数据库服务获取用户任务，支持分页
            db_tasks = db_service.get_user_tasks(user_id, limit, offset)
            logger.info(f"从数据库获取用户任务: 用户ID={user_id}, 任务数={len(db_tasks)}")
            
            # 获取每个任务的详细信息
            for db_task in db_tasks:
                task_id = db_task.get('id')
                task = db_task.copy()
                
                # 添加文件信息
                task['files'] = db_service.get_task_files(task_id)
                
                tasks.append(task)
                
            return tasks
        except Exception as e:
            logger.error(f"获取用户任务列表失败: {str(e)}")
            # 使用内存存储作为备选
            memory_tasks = []
            for task_id, task in self.in_memory_tasks.items():
                if task.get("user_id") == user_id:
                    task_copy = task.copy()
                    memory_tasks.append(task_copy)
            
            # 手动处理分页
            sorted_tasks = sorted(memory_tasks, key=lambda x: x.get("created_at", ""), reverse=True)
            page_tasks = sorted_tasks[offset:offset + limit]
            logger.debug(f"内存模式(备选): 获取用户任务: 用户ID={user_id}, 任务数={len(page_tasks)}")
            return page_tasks
    
    async def update_task_status(self, task_id: int, status: str, logs: Optional[str] = None) -> bool:
        """更新任务状态"""
        try:
            if not db_service.db_available:
                # 如果数据库不可用，使用内存存储
                if str(task_id) in self.in_memory_tasks:
                    self.in_memory_tasks[str(task_id)]["status"] = status
                    self.in_memory_tasks[str(task_id)]["updated_at"] = datetime.now().isoformat()
                    if logs:
                        # 如果提供了日志，也更新日志
                        if str(task_id) not in self.in_memory_logs:
                            self.in_memory_logs[str(task_id)] = ""
                        self.in_memory_logs[str(task_id)] += logs + "\n"
                    logger.info(f"内存模式: 更新任务状态成功: ID={task_id}, 状态={status}")
                    return True
                else:
                    logger.warning(f"内存模式: 更新任务状态失败: 找不到任务 ID={task_id}")
                    return False
            
            # 使用数据库服务更新状态
            result = db_service.update_task_status(task_id, status)
            
            # 如果提供了日志，也更新日志
            if logs and result:
                await self.append_task_logs(task_id, logs)
                
            return result
        except Exception as e:
            logger.error(f"更新任务状态失败: {str(e)}")
            # 尝试使用内存存储
            if str(task_id) in self.in_memory_tasks:
                self.in_memory_tasks[str(task_id)]["status"] = status
                self.in_memory_tasks[str(task_id)]["updated_at"] = datetime.now().isoformat()
                if logs:
                    if str(task_id) not in self.in_memory_logs:
                        self.in_memory_logs[str(task_id)] = ""
                    self.in_memory_logs[str(task_id)] += logs + "\n"
                logger.info(f"内存模式(备选): 更新任务状态成功: ID={task_id}, 状态={status}")
                return True
            else:
                # 如果内存中也找不到，创建一个新任务
                self.in_memory_tasks[str(task_id)] = {
                    "id": task_id,
                    "user_id": "unknown",
                    "prompt": "",
                    "status": status,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                if logs:
                    self.in_memory_logs[str(task_id)] = logs + "\n"
                logger.info(f"内存模式(备选): 创建并更新任务状态: ID={task_id}, 状态={status}")
                return True
    
    async def append_task_logs(self, task_id: int, log_content: str) -> bool:
        """追加任务日志"""
        try:
            if not db_service.db_available:
                # 如果数据库不可用，使用内存存储
                if str(task_id) not in self.in_memory_logs:
                    self.in_memory_logs[str(task_id)] = ""
                self.in_memory_logs[str(task_id)] += log_content + "\n"
                logger.debug(f"内存模式: 追加任务日志成功: ID={task_id}")
                return True
                
            # 先获取现有日志
            task = db_service.get_task(task_id)
            if not task:
                logger.warning(f"追加日志失败: 任务不存在 ID={task_id}")
                return False
                
            # 获取现有日志URL
            log_url = task.get('log_url')
            if log_url:
                # 尝试下载现有日志
                try:
                    existing_log = await cos_service.download_file(log_url)
                    if existing_log:
                        # 追加新日志
                        updated_log = existing_log + "\n" + log_content
                        # 重新上传
                        new_log_url = await cos_service.upload_text(
                            f"task_{task_id}_log.txt", 
                            updated_log, 
                            f"tasks/{task_id}/logs/"
                        )
                        # 更新数据库记录
                        db_service.update_task_log_url(task_id, new_log_url)
                        return True
                except Exception as cos_err:
                    logger.error(f"下载或上传日志失败: {str(cos_err)}")
                    # 如果COS操作失败，尝试保存到本地
                    local_log_path = f"logs/task_{task_id}.log"
                    os.makedirs(os.path.dirname(local_log_path), exist_ok=True)
                    try:
                        with open(local_log_path, 'a', encoding='utf-8') as f:
                            f.write(log_content + "\n")
                        return True
                    except Exception as file_err:
                        logger.error(f"保存日志到本地文件失败: {str(file_err)}")
                        # 如果所有方法都失败，保存到内存
                        if str(task_id) not in self.in_memory_logs:
                            self.in_memory_logs[str(task_id)] = ""
                        self.in_memory_logs[str(task_id)] += log_content + "\n"
                        return True
            
            # 如果没有现有日志，创建新日志
            log_content_with_timestamp = f"[{datetime.now().isoformat()}] {log_content}"
            log_url = await cos_service.upload_text(
                f"task_{task_id}_log.txt", 
                log_content_with_timestamp, 
                f"tasks/{task_id}/logs/"
            )
            # 更新数据库记录
            db_service.update_task_log_url(task_id, log_url)
            return True
            
        except Exception as e:
            logger.error(f"追加任务日志失败: {str(e)}")
            # 失败时保存到内存
            if str(task_id) not in self.in_memory_logs:
                self.in_memory_logs[str(task_id)] = ""
            self.in_memory_logs[str(task_id)] += log_content + "\n"
            logger.debug(f"内存模式(备选): 追加任务日志: ID={task_id}")
            return True
    
    async def save_task_logs(self, task_id: int, logs: str) -> str:
        """将日志内容保存为文件并上传到COS，返回COS URL"""
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_file:
                temp_file.write(logs)
                temp_file_path = temp_file.name
            
            try:
                # 上传到COS
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"task_{task_id}_log_{timestamp}.txt"
                
                # 读取文件内容
                with open(temp_file_path, 'rb') as f:
                    file_content = f.read()
                
                # 上传文件
                upload_result = await cos_service.upload_file(
                    file_content=file_content,
                    filename=filename,
                    content_type="text/plain",
                    task_id=str(task_id)
                )
                
                logger.info(f"日志文件上传成功: {upload_result['url']}")
                return upload_result['url']
            finally:
                # 删除临时文件
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
        except Exception as e:
            logger.error(f"保存任务日志失败: {str(e)}")
            raise
    
    async def get_task_log_content(self, task_id: int) -> Optional[str]:
        """从COS获取任务日志内容"""
        try:
            # 获取任务信息
            task = db_service.get_task(task_id)
            if not task or not task.get('log_url'):
                return None
            
            # 从COS下载日志内容
            log_content = await cos_service.download_file(task['log_url'])
            
            # 将二进制内容转换为文本
            return log_content.decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"获取任务日志内容失败: {str(e)}")
            raise
    
    async def scan_and_upload_task_files(self, task_id: int, directory: str, pattern: str = "*") -> List[Dict[str, Any]]:
        """扫描目录中的文件并上传到COS"""
        try:
            uploaded_files = []
            
            # 获取任务信息
            task = await self.get_task(task_id)
            if not task:
                raise ValueError(f"任务不存在: {task_id}")
            
            # 扫描目录
            file_paths = glob.glob(os.path.join(directory, pattern))
            logger.info(f"扫描到 {len(file_paths)} 个文件: 任务ID={task_id}, 目录={directory}")
            
            for file_path in file_paths:
                if not os.path.isfile(file_path):
                    continue
                
                try:
                    # 上传文件到COS
                    upload_result = await cos_service.upload_local_file(
                        filepath=file_path,
                        task_id=str(task_id)
                    )
                    
                    # 创建文件记录
                    file_id = db_service.create_file(
                        task_id=task_id,
                        filename=upload_result['filename'],
                        cos_url=upload_result['url'],
                        content_type=upload_result['content_type'],
                        file_size=upload_result['size']
                    )
                    
                    # 添加到结果列表
                    uploaded_files.append({
                        'id': file_id,
                        'filename': upload_result['filename'],
                        'cos_url': upload_result['url'],
                        'content_type': upload_result['content_type'],
                        'file_size': upload_result['size']
                    })
                    
                    logger.info(f"文件上传成功: {file_path} -> {upload_result['url']}")
                except Exception as file_error:
                    logger.error(f"文件上传失败: {file_path}, 错误: {str(file_error)}")
            
            return uploaded_files
        except Exception as e:
            logger.error(f"扫描和上传任务文件失败: {str(e)}")
            raise
    
    async def upload_file_to_task(self, task_id: int, file_content: bytes, filename: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        """上传文件到任务"""
        try:
            # 使用COS服务上传文件
            if not cos_service._initialized:
                logger.warning(f"COS服务未初始化，无法上传文件")
                return None
            
            # 上传文件
            result = await cos_service.upload_file(
                file_content=file_content,
                filename=filename,
                content_type=content_type,
                task_id=str(task_id)
            )
            
            if not result:
                logger.error(f"上传文件失败: 无效的COS上传结果")
                return None
                
            # 保存文件记录到数据库
            if db_service.db_available:
                file_id = db_service.add_file(
                    task_id=task_id,
                    filename=filename,
                    file_url=result["url"],
                    content_type=content_type or ""
                )
                
                if file_id:
                    # 添加ID到结果
                    result["id"] = file_id
                    return result
                    
            # 如果数据库不可用，使用内存存储
            file_id = str(uuid.uuid4())
            file_record = {
                "id": file_id,
                "task_id": task_id,
                "filename": filename,
                "file_url": result["url"],
                "content_type": content_type or "",
                "created_at": datetime.now().isoformat()
            }
            
            self.in_memory_files[file_id] = file_record
            
            # 将文件记录与任务关联
            if str(task_id) in self.in_memory_tasks:
                if "files" not in self.in_memory_tasks[str(task_id)]:
                    self.in_memory_tasks[str(task_id)]["files"] = []
                self.in_memory_tasks[str(task_id)]["files"].append(file_record)
                
            # 添加ID到结果
            result["id"] = file_id
            return result
            
        except Exception as e:
            logger.error(f"上传文件失败: {str(e)}")
            return None
            
    async def upload_local_file(self, task_id: str, filepath: str, target_filename: str = None) -> Dict[str, Any]:
        """上传本地文件到任务，并保存到数据库
        
        Args:
            task_id: 任务ID
            filepath: 本地文件路径
            target_filename: 目标文件名（可选）
            
        Returns:
            包含文件信息的字典，如果失败则返回None
        """
        try:
            if not os.path.exists(filepath):
                logger.error(f"上传文件失败: 文件不存在 {filepath}")
                return None
                
            # 使用COS服务上传文件
            if not cos_service._initialized:
                logger.warning(f"COS服务未初始化，无法上传文件")
                return None
                
            # 获取默认文件名（如果未提供目标文件名）
            if not target_filename:
                target_filename = os.path.basename(filepath)
                
            # 上传文件到COS
            result = await cos_service.upload_local_file(
                filepath=filepath,
                task_id=str(task_id),
                target_filename=target_filename
            )
            
            if not result:
                logger.error(f"上传文件失败: 无效的COS上传结果")
                return None
                
            # 获取内容类型
            content_type = result.get("content_type", "")
                
            # 保存文件记录到数据库
            if db_service.db_available:
                file_id = db_service.add_file(
                    task_id=task_id,
                    filename=target_filename,
                    file_url=result["url"],
                    content_type=content_type
                )
                
                if file_id:
                    # 添加ID到结果
                    result["id"] = file_id
                    result["filename"] = target_filename
                    result["cos_url"] = result["url"]
                    return result
                    
            # 如果数据库不可用，使用内存存储
            file_id = str(uuid.uuid4())
            file_record = {
                "id": file_id,
                "task_id": task_id,
                "filename": target_filename,
                "file_url": result["url"],
                "content_type": content_type,
                "created_at": datetime.now().isoformat()
            }
            
            self.in_memory_files[file_id] = file_record
            
            # 将文件记录与任务关联
            if str(task_id) in self.in_memory_tasks:
                if "files" not in self.in_memory_tasks[str(task_id)]:
                    self.in_memory_tasks[str(task_id)]["files"] = []
                self.in_memory_tasks[str(task_id)]["files"].append(file_record)
                
            # 构建返回结果
            return {
                "id": file_id,
                "filename": target_filename,
                "cos_url": result["url"],
                "content_type": content_type,
                "size": result.get("size", 0)
            }
            
        except Exception as e:
            logger.error(f"上传本地文件失败: {str(e)}")
            return None
    
    async def get_task_files(self, task_id: int) -> List[Dict[str, Any]]:
        """获取任务的文件列表"""
        try:
            # 如果数据库可用，从数据库获取文件列表
            if db_service.db_available:
                files = db_service.get_task_files(task_id)
                logger.debug(f"从数据库获取任务文件: ID={task_id}, 文件数={len(files)}")
                return files
                
            # 如果数据库不可用，从内存获取文件列表
            files = []
            for file_id, file in self.in_memory_files.items():
                if file.get("task_id") == str(task_id):
                    files.append(file)
            
            logger.debug(f"内存模式: 获取任务文件: ID={task_id}, 文件数={len(files)}")
            return files
            
        except Exception as e:
            logger.error(f"获取任务文件列表失败: {str(e)}")
            return []
            
    async def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """获取单个文件的详细信息"""
        try:
            # 如果数据库可用，从数据库获取文件
            if db_service.db_available:
                file = db_service.get_file(file_id)
                if file:
                    logger.debug(f"从数据库获取文件: ID={file_id}")
                    return file
                    
            # 如果数据库不可用或文件不存在，尝试从内存获取
            if str(file_id) in self.in_memory_files:
                file = self.in_memory_files[str(file_id)]
                logger.debug(f"内存模式: 获取文件: ID={file_id}")
                return file
                
            logger.warning(f"文件不存在: ID={file_id}")
            return None
            
        except Exception as e:
            logger.error(f"获取文件失败: {str(e)}")
            return None
    
    async def download_task_file(self, file_id: int) -> Optional[Dict[str, Any]]:
        """下载任务文件"""
        try:
            # 获取文件信息
            file_info = db_service.get_file(file_id)
            if not file_info:
                logger.warning(f"文件不存在: ID={file_id}")
                return None
            
            # 从COS下载文件内容
            file_content = await cos_service.download_file(file_info['cos_url'])
            
            # 组装结果
            result = {
                'id': file_info['id'],
                'task_id': file_info['task_id'],
                'filename': file_info['filename'],
                'content_type': file_info['content_type'],
                'content': file_content,
                'size': file_info['file_size']
            }
            
            return result
        except Exception as e:
            logger.error(f"下载任务文件失败: {str(e)}")
            raise
    
    async def delete_task(self, task_id: int) -> bool:
        """删除任务及其关联文件"""
        try:
            # 获取任务信息
            task = await self.get_task(task_id)
            if not task:
                return False
            
            # 删除日志文件（如果存在）
            if task.get('log_url'):
                try:
                    cos_service.delete_file(task['log_url'])
                except Exception as log_error:
                    logger.error(f"删除日志文件失败: {task['log_url']}, 错误: {str(log_error)}")
            
            # 获取任务文件
            files = await self.get_task_files(task_id)
            
            # 删除COS上的文件
            for file in files:
                try:
                    cos_service.delete_file(file['cos_url'])
                except Exception as file_error:
                    logger.error(f"删除COS文件失败: {file['cos_url']}, 错误: {str(file_error)}")
            
            # 删除任务记录（数据库文件记录会通过外键级联删除）
            success = db_service.delete_task(task_id)
            
            if success:
                logger.info(f"删除任务成功: ID={task_id}")
            else:
                logger.warning(f"删除任务失败: ID={task_id}")
            
            return success
        except Exception as e:
            logger.error(f"删除任务失败: {str(e)}")
            raise

    async def get_task_logs(self, task_id: int) -> List[Dict[str, Any]]:
        """获取任务的日志列表"""
        try:
            logs = []
            logger.debug(f"获取任务 {task_id} 的日志")
            
            # 如果数据库可用，从数据库获取任务信息
            if db_service.db_available:
                task = db_service.get_task(task_id)
                if not task:
                    logger.warning(f"获取日志失败：找不到任务 ID={task_id}")
                    return []
                    
                # 如果任务有日志URL，尝试下载日志内容
                if task.get('log_url'):
                    try:
                        log_content = await cos_service.download_file(task['log_url'])
                        if log_content:
                            # 将日志内容解析为日志项列表
                            log_lines = log_content.strip().split('\n')
                            for line in log_lines:
                                if not line.strip():
                                    continue
                                    
                                try:
                                    # 尝试解析为JSON（如果是结构化日志）
                                    import json
                                    log_item = json.loads(line)
                                    logs.append(log_item)
                                except json.JSONDecodeError:
                                    # 如果不是JSON，按普通文本处理
                                    timestamp = datetime.now().isoformat()
                                    if '[' in line and ']' in line:
                                        # 尝试提取时间戳
                                        try:
                                            timestamp_str = line.split('[')[1].split(']')[0]
                                            timestamp = datetime.fromisoformat(timestamp_str).isoformat()
                                            message = line.split(']', 1)[1].strip()
                                        except:
                                            message = line
                                    else:
                                        message = line
                                    
                                    logs.append({
                                        'timestamp': timestamp,
                                        'level': 'info',
                                        'message': message
                                    })
                    except Exception as e:
                        logger.error(f"下载日志内容失败: {str(e)}")
                        # 添加一个错误日志项
                        logs.append({
                            'timestamp': datetime.now().isoformat(),
                            'level': 'error',
                            'message': f"无法获取日志: {str(e)}"
                        })
            
            # 如果数据库不可用或没有获取到日志，尝试从内存获取
            if not logs and str(task_id) in self.in_memory_logs:
                log_content = self.in_memory_logs[str(task_id)]
                log_lines = log_content.strip().split('\n')
                for line in log_lines:
                    if not line.strip():
                        continue
                        
                    # 简单解析日志行
                    timestamp = datetime.now().isoformat()
                    level = 'info'
                    
                    # 尝试提取级别和时间戳
                    if '[' in line:
                        parts = line.split('[')
                        if len(parts) > 2:
                            try:
                                timestamp_str = parts[1].split(']')[0]
                                timestamp = datetime.fromisoformat(timestamp_str).isoformat()
                                if len(parts) > 3:
                                    level_str = parts[2].split(']')[0].lower()
                                    if level_str in ['info', 'error', 'warning', 'debug']:
                                        level = level_str
                                message = line.split(']', 2)[-1].strip()
                            except:
                                message = line
                        else:
                            message = line
                    else:
                        message = line
                    
                    logs.append({
                        'timestamp': timestamp,
                        'level': level,
                        'message': message
                    })
            
            # 确保日志按时间排序
            logs.sort(key=lambda x: x.get('timestamp', ''), reverse=False)
            
            logger.debug(f"获取到 {len(logs)} 条日志")
            return logs
        except Exception as e:
            logger.error(f"获取任务日志失败: {str(e)}")
            return [{
                'timestamp': datetime.now().isoformat(),
                'level': 'error',
                'message': f"获取日志时出错: {str(e)}"
            }]

# 创建单例实例
task_service = TaskService() 