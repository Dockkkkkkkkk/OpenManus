from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import StreamingResponse
from typing import List, Optional
import json
import os
import logging
from datetime import datetime

from app.auth import get_user_id, Web
from app.services.task_service import task_service
from app.models.task import Task, TaskSummary, TaskFile

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/tasks",
    tags=["tasks"],
)

# 获取用户任务列表
@router.get("/", response_model=List[TaskSummary])
@Web()
async def get_user_tasks(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    user_id: str = Depends(get_user_id)
):
    """获取当前用户的任务列表"""
    try:
        tasks = await task_service.get_user_tasks(user_id, limit, offset)
        return tasks
    except Exception as e:
        logger.error(f"获取用户任务列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")

# 获取任务详情
@router.get("/{task_id}", response_model=Task)
@Web()
async def get_task(
    task_id: int,
    request: Request,
    user_id: str = Depends(get_user_id)
):
    """获取任务详情"""
    try:
        task = await task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        # 检查任务所有权
        if task["user_id"] != user_id:
            # 管理员可以访问所有任务（未来可添加管理员检查）
            # if not is_admin(user_id):
            raise HTTPException(status_code=403, detail="无权访问此任务")
        
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务详情失败: {str(e)}")

# 创建任务
@router.post("/", response_model=dict)
@Web()
async def create_task(
    request: Request,
    prompt: str,
    user_id: str = Depends(get_user_id)
):
    """创建新任务"""
    try:
        task_id = await task_service.create_task(user_id, prompt)
        return {"id": task_id, "user_id": user_id, "prompt": prompt, "status": "pending"}
    except Exception as e:
        logger.error(f"创建任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")

# 获取任务文件列表
@router.get("/{task_id}/files", response_model=List[TaskFile])
@Web()
async def get_task_files(
    task_id: int,
    request: Request,
    user_id: str = Depends(get_user_id)
):
    """获取任务的文件列表"""
    try:
        # 检查任务存在并验证权限
        task = await task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        if task["user_id"] != user_id:
            # 管理员可以访问所有任务（未来可添加管理员检查）
            # if not is_admin(user_id):
            raise HTTPException(status_code=403, detail="无权访问此任务")
        
        # 获取文件列表
        files = await task_service.get_task_files(task_id)
        return files
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务文件列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务文件列表失败: {str(e)}")

# 下载任务文件
@router.get("/{task_id}/files/{file_id}/download")
@Web()
async def download_task_file(
    task_id: int,
    file_id: int,
    request: Request,
    user_id: str = Depends(get_user_id)
):
    """下载任务文件"""
    try:
        # 检查任务存在并验证权限
        task = await task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        if task["user_id"] != user_id:
            # 管理员可以访问所有任务（未来可添加管理员检查）
            # if not is_admin(user_id):
            raise HTTPException(status_code=403, detail="无权访问此任务")
        
        # 下载文件
        file_info = await task_service.download_task_file(file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
        
        # 将文件作为流式响应返回
        return StreamingResponse(
            iter([file_info["content"]]),
            media_type=file_info["content_type"] or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{file_info["filename"]}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载任务文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载任务文件失败: {str(e)}")

# 删除任务
@router.delete("/{task_id}")
@Web()
async def delete_task(
    task_id: int,
    request: Request,
    user_id: str = Depends(get_user_id)
):
    """删除任务及其关联文件"""
    try:
        # 检查任务存在并验证权限
        task = await task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        if task["user_id"] != user_id:
            # 管理员可以删除所有任务（未来可添加管理员检查）
            # if not is_admin(user_id):
            raise HTTPException(status_code=403, detail="无权删除此任务")
        
        # 删除任务
        success = await task_service.delete_task(task_id)
        if not success:
            raise HTTPException(status_code=500, detail=f"删除任务失败: {task_id}")
        
        return {"message": "任务删除成功", "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")

# 扫描并上传任务目录文件
@router.post("/{task_id}/scan-files", response_model=List[TaskFile])
@Web()
async def scan_and_upload_files(
    task_id: int,
    request: Request,
    directory: str,
    user_id: str = Depends(get_user_id),
    pattern: str = "*"
):
    """扫描目录并上传文件到任务"""
    try:
        # 检查任务存在并验证权限
        task = await task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        if task["user_id"] != user_id:
            # 管理员可以管理所有任务（未来可添加管理员检查）
            # if not is_admin(user_id):
            raise HTTPException(status_code=403, detail="无权管理此任务")
        
        # 验证目录路径安全性
        if ".." in directory or not os.path.exists(directory):
            raise HTTPException(status_code=400, detail=f"无效的目录路径: {directory}")
        
        # 扫描并上传文件
        uploaded_files = await task_service.scan_and_upload_task_files(task_id, directory, pattern)
        return uploaded_files
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"扫描并上传任务文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"扫描并上传任务文件失败: {str(e)}")

# 更新任务状态
@router.put("/{task_id}/status")
@Web()
async def update_task_status(
    task_id: int,
    request: Request,
    status: str,
    user_id: str = Depends(get_user_id),
    logs: Optional[str] = None
):
    """更新任务状态"""
    try:
        # 检查任务存在并验证权限
        task = await task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        if task["user_id"] != user_id:
            # 管理员可以管理所有任务（未来可添加管理员检查）
            # if not is_admin(user_id):
            raise HTTPException(status_code=403, detail="无权管理此任务")
        
        # 验证状态值
        valid_statuses = ["pending", "running", "completed", "failed"]
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")
        
        # 更新状态
        success = await task_service.update_task_status(task_id, status, logs)
        if not success:
            raise HTTPException(status_code=500, detail=f"更新任务状态失败: {task_id}")
        
        return {"message": "任务状态更新成功", "task_id": task_id, "status": status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新任务状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新任务状态失败: {str(e)}")

# 追加任务日志
@router.post("/{task_id}/logs")
@Web()
async def append_task_logs(
    task_id: int,
    request: Request,
    log_content: str,
    user_id: str = Depends(get_user_id)
):
    """追加任务日志"""
    try:
        # 检查任务存在并验证权限
        task = await task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        if task["user_id"] != user_id:
            # 管理员可以管理所有任务（未来可添加管理员检查）
            # if not is_admin(user_id):
            raise HTTPException(status_code=403, detail="无权管理此任务")
        
        # 追加日志
        success = await task_service.append_task_logs(task_id, log_content)
        if not success:
            raise HTTPException(status_code=500, detail=f"追加任务日志失败: {task_id}")
        
        return {"message": "任务日志追加成功", "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"追加任务日志失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"追加任务日志失败: {str(e)}") 