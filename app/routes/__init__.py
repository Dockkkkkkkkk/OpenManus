"""路由包

包含应用程序所有路由模块
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.auth import Web
import os
import traceback
import json
from datetime import datetime

# 创建路由器
router = APIRouter(tags=["pages"])

# 设置模板
# 获取当前文件所在目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取app目录的路径
app_dir = os.path.dirname(current_dir)
# 设置模板目录为app/templates
template_dir = os.path.join(app_dir, "templates")
templates = Jinja2Templates(directory=template_dir)

# 自定义JSON编码器，处理datetime对象
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# 辅助函数，将字典中的datetime对象转换为字符串
def convert_datetime_to_iso(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {key: convert_datetime_to_iso(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [convert_datetime_to_iso(item) for item in obj]
    return obj

@router.get('/tasks')
@Web()  # 使用Web装饰器替代auth_required
async def tasks_page(request: Request):
    """
    任务管理API
    返回用户的所有任务列表
    """
    try:
        # 从请求状态中获取用户信息
        user_info = getattr(request.state, "user", None)
        if not user_info:
            return JSONResponse({"error": "需要登录", "message": "请登录后再访问此功能"})
            
        # 获取用户ID
        user_id = user_info.get("user_id", "")
        if not user_id:
            return JSONResponse({"error": "无效的用户信息", "message": "无法获取用户ID"})
        
        # 检查URL参数中是否有分页参数
        limit = int(request.query_params.get('limit', '20'))
        offset = int(request.query_params.get('offset', '0'))
            
        # 使用任务服务获取任务列表
        from app.services.task_service import task_service
        tasks = await task_service.get_user_tasks(user_id, limit=limit, offset=offset)
        
        # 记录日志
        print(f"从数据库获取到 {len(tasks)} 个任务，用户ID: {user_id}")
        
        # 转换datetime对象为ISO格式字符串
        serializable_tasks = convert_datetime_to_iso(tasks)
        
        # 返回JSON响应
        return JSONResponse(serializable_tasks)
    except Exception as e:
        print(f"获取任务列表失败: {str(e)}")
        print(traceback.format_exc())
        return JSONResponse({"error": "获取任务失败", "message": str(e)})

@router.get('/tasks/{task_id}')
@Web()
async def task_detail_page(request: Request, task_id: int):
    """
    任务详情页面
    显示特定任务的详细信息
    """
    # 检查URL参数中是否有auth_token
    auth_token = request.query_params.get('auth_token')
    
    # 检查URL参数中是否直接提供了用户信息
    user_id = request.query_params.get('user_id')
    username = request.query_params.get('username')
    
    # 如果提供了用户信息，直接添加到request.state，完整设置所有可能需要的字段
    if user_id and username:
        # 创建完整的用户信息对象
        request.state.user = {
            "id": user_id,
            "user_id": user_id,
            "username": username,
            "is_admin": True,  # 如果有必要，可以从URL参数获取
            "avatar": "",
            "email": "",
            "roles": []
        }
        # 直接返回模板，跳过验证过程
        return templates.TemplateResponse("task_detail.html", {"request": request, "task_id": task_id})
    # 如果提供了token，添加到请求头
    elif auth_token:
        request.headers.__dict__["_list"].append(
            (b'authorization', f'Bearer {auth_token}'.encode())
        )
    
    # 正常处理
    return templates.TemplateResponse("task_detail.html", {"request": request, "task_id": task_id})

# 空的__init__.py文件，使routes目录成为Python包 