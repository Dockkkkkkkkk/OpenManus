from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid

class TaskCreate(BaseModel):
    """创建任务的请求模型"""
    prompt: str
    user_id: str

class TaskStatus(BaseModel):
    """任务状态更新模型"""
    status: str
    logs: Optional[str] = None

class TaskFile(BaseModel):
    """任务文件模型"""
    id: int = Field(default=None)
    task_id: int
    filename: str
    cos_url: str
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        orm_mode = True

class Task(BaseModel):
    """任务模型"""
    id: int = Field(default=None)
    user_id: str
    prompt: str
    status: str
    logs: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    files: List[TaskFile] = []
    
    class Config:
        orm_mode = True

class TaskSummary(BaseModel):
    """任务概要模型（用于列表展示）"""
    id: int
    user_id: str
    prompt: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    file_count: int = 0
    
    class Config:
        orm_mode = True 