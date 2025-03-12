from qcloud_cos import CosConfig, CosS3Client
import sys
import logging
import os
from datetime import datetime, timezone
import io
import tempfile
from fastapi import UploadFile
import uuid

# 导入配置
from app.config.database import COSConfig

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class COSService:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(COSService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 检查配置是否完整
        if not COSConfig.is_configured():
            logger.warning("COS配置不完整，文件上传功能可能无法正常工作")
            self._initialized = False
            return
        
        # 初始化COS客户端
        self.config = CosConfig(
            Region=COSConfig.REGION,
            SecretId=COSConfig.SECRET_ID,
            SecretKey=COSConfig.SECRET_KEY,
            Token=None,
            Scheme='https',
            Timeout=60
        )
        self.client = CosS3Client(self.config)
        self._initialized = True
        logger.info("COS服务初始化完成")
    
    def ensure_bucket_exists(self):
        """确保存储桶存在"""
        try:
            # 检查存储桶是否存在
            self.client.head_bucket(Bucket=COSConfig.BUCKET)
            logger.info(f"存储桶 {COSConfig.BUCKET} 已存在")
        except Exception as e:
            logger.warning(f"存储桶 {COSConfig.BUCKET} 不存在，尝试创建: {str(e)}")
            try:
                # 创建存储桶
                self.client.create_bucket(
                    Bucket=COSConfig.BUCKET
                )
                logger.info(f"存储桶 {COSConfig.BUCKET} 创建成功")
            except Exception as create_error:
                logger.error(f"创建存储桶失败: {str(create_error)}")
                raise
    
    def get_object_key(self, file_url: str) -> str:
        """从完整的 COS URL 中提取对象键"""
        url_prefix = COSConfig.get_url_prefix()
        if file_url.startswith(url_prefix):
            file_name = file_url[len(url_prefix):]
        else:
            raise ValueError(f"URL不以预期的前缀开头: {url_prefix}")
        return file_name.lstrip('/')
    
    def get_file_url(self, file_name: str) -> str:
        """根据文件名生成完整的 COS URL"""
        if file_name.startswith("/"):
            file_name = file_name[1:]
        return f"{COSConfig.get_url_prefix()}/{file_name}"
    
    async def upload_file(self, file_content: bytes, filename: str, content_type: str = None, task_id: str = None) -> dict:
        """
        上传文件到 COS
        :param file_content: 文件内容（字节）
        :param filename: 文件名
        :param content_type: 文件类型
        :param task_id: 任务ID，用于组织文件
        :return: 包含文件URL和对象键的字典
        """
        try:
            # 确保存储桶存在
            self.ensure_bucket_exists()
            
            # 生成唯一的文件名
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
            file_id = str(uuid.uuid4())[:8]
            
            # 处理文件名，移除特殊字符
            safe_filename = "".join([c for c in filename if c.isalnum() or c in "._- "])
            safe_filename = safe_filename.replace(" ", "_")
            
            unique_filename = f"{timestamp}_{file_id}_{safe_filename}"
            
            # 构建对象键
            prefix = f"tasks/{task_id}" if task_id else "uploads"
            object_key = f"{prefix}/{unique_filename}"
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            
            try:
                # 使用高级上传接口
                self.client.upload_file(
                    Bucket=COSConfig.BUCKET,
                    LocalFilePath=temp_file_path,
                    Key=object_key,
                    ContentType=content_type,
                    PartSize=5,  # 5MB 分片
                    MAXThread=10,
                    EnableMD5=False
                )
                
                file_url = self.get_file_url(object_key)
                file_size = os.path.getsize(temp_file_path)
                
                logger.info(f"文件上传成功: {object_key}")
                return {
                    "url": file_url,
                    "key": object_key,
                    "filename": filename,
                    "content_type": content_type,
                    "size": file_size
                }
                
            finally:
                # 清理临时文件
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                    logger.info(f"临时文件已删除: {temp_file_path}")
            
        except Exception as e:
            logger.error(f"上传文件到COS失败: {str(e)}")
            raise
    
    async def upload_local_file(self, filepath: str, task_id: str = None, target_filename: str = None) -> dict:
        """上传本地文件到COS"""
        try:
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"文件不存在: {filepath}")
            
            # 读取文件内容
            with open(filepath, 'rb') as f:
                file_content = f.read()
            
            # 获取文件名和类型
            filename = target_filename or os.path.basename(filepath)
            content_type = self._guess_content_type(filename)
            
            # 上传文件
            result = await self.upload_file(
                file_content=file_content,
                filename=filename,
                content_type=content_type,
                task_id=task_id
            )
            
            # 删除本地文件
            os.remove(filepath)
            logger.info(f"本地文件已删除: {filepath}")
            
            return result
            
        except Exception as e:
            logger.error(f"上传本地文件失败: {str(e)}")
            raise
    
    def delete_file(self, file_url: str) -> bool:
        """从COS删除文件"""
        try:
            object_key = self.get_object_key(file_url)
            self.client.delete_object(
                Bucket=COSConfig.BUCKET,
                Key=object_key
            )
            logger.info(f"文件删除成功: {object_key}")
            return True
        except Exception as e:
            logger.error(f"从COS删除文件失败: {e}")
            return False
    
    async def download_file(self, file_url: str) -> bytes:
        """从COS下载文件"""
        try:
            # 直接从URL中提取对象键，跳过前缀验证
            try:
                # 原始方法：通过前缀验证
                object_key = self.get_object_key(file_url)
            except ValueError as e:
                # 如果前缀验证失败，则尝试直接解析URL
                logger.warning(f"URL前缀验证失败，尝试直接下载: {e}")
                # 从URL中提取文件路径
                if "myqcloud.com" in file_url:
                    # 对于腾讯云COS URL，提取域名后面的路径
                    parts = file_url.split(".com/", 1)
                    if len(parts) > 1:
                        object_key = parts[1]
                    else:
                        object_key = file_url.split("/")[-1]  # 只取文件名
                else:
                    # 对于其他URL，直接使用最后一部分作为对象键
                    object_key = file_url.split("/")[-1]
                
                logger.info(f"直接提取的对象键: {object_key}")
            
            # 尝试下载文件
            try:
                response = self.client.get_object(
                    Bucket=COSConfig.BUCKET,
                    Key=object_key
                )
                logger.info(f"成功从COS下载文件: {object_key}")
                return response['Body'].get_raw_stream().read()
            except Exception as cos_error:
                # 如果COS下载失败，尝试直接HTTP请求获取文件
                logger.warning(f"从COS下载失败，尝试HTTP请求: {cos_error}")
                import httpx
                async with httpx.AsyncClient() as client:
                    http_response = await client.get(file_url)
                    if http_response.status_code == 200:
                        logger.info(f"通过HTTP成功下载文件: {file_url}")
                        return http_response.content
                    else:
                        raise Exception(f"HTTP下载失败: {http_response.status_code}")
        except Exception as e:
            logger.error(f"从COS下载文件失败: {e}")
            # 返回默认的空内容，而不是抛出异常
            return b""
    
    async def upload_text(self, filename: str, text_content: str, prefix: str = "uploads/") -> str:
        """
        上传文本内容到COS
        :param filename: 文件名
        :param text_content: 文本内容
        :param prefix: 存储路径前缀
        :return: 文件的COS URL
        """
        try:
            # 确保存储桶存在
            self.ensure_bucket_exists()
            
            # 将文本内容转换为字节
            content_bytes = text_content.encode('utf-8')
            
            # 构建对象键，确保前缀有正确的格式
            if not prefix.endswith('/'):
                prefix += '/'
            object_key = f"{prefix}{filename}"
            
            # 使用内存流上传
            with io.BytesIO(content_bytes) as file_stream:
                self.client.put_object(
                    Bucket=COSConfig.BUCKET,
                    Body=file_stream,
                    Key=object_key,
                    ContentType='text/plain; charset=utf-8'
                )
            
            # 返回文件URL
            file_url = self.get_file_url(object_key)
            logger.info(f"文本内容上传成功: {object_key}")
            return file_url
            
        except Exception as e:
            logger.error(f"上传文本内容到COS失败: {str(e)}")
            raise
    
    def _guess_content_type(self, filename: str) -> str:
        """根据文件扩展名猜测内容类型"""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        content_types = {
            'txt': 'text/plain',
            'html': 'text/html',
            'css': 'text/css',
            'js': 'application/javascript',
            'json': 'application/json',
            'xml': 'application/xml',
            'pdf': 'application/pdf',
            'zip': 'application/zip',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'webp': 'image/webp',
            'mp3': 'audio/mpeg',
            'wav': 'audio/wav',
            'mp4': 'video/mp4',
            'py': 'text/x-python',
            'md': 'text/markdown',
        }
        return content_types.get(ext, 'application/octet-stream')


# 单例实例
cos_service = COSService() 