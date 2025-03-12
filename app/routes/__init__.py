"""路由包

包含应用程序所有路由模块
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.auth import Web

# 创建路由器
router = APIRouter(tags=["pages"])

# 设置模板
templates = Jinja2Templates(directory="templates")

@router.get('/tasks')
@Web()  # 使用Web装饰器替代auth_required
async def tasks_page(request: Request):
    """
    任务管理页面
    显示用户的所有任务和详情
    """
    return templates.TemplateResponse("tasks.html", {"request": request})

# 空的__init__.py文件，使routes目录成为Python包 