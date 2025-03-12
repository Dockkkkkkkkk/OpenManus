from functools import wraps
from fastapi import Request
from fastapi.responses import JSONResponse
import httpx
import inspect

# 存储需要认证和公开的路由路径
authenticated_routes = set()
public_routes = set()

# 认证基础URL，将在应用启动时从配置中设置
AUTH_BASE_URL = None

def require_auth(func):
    """
    标记需要认证的路由的装饰器
    用法: @require_auth
    """
    path = "/" + func.__name__
    # 检查原始函数是否有路径参数
    if hasattr(func, "__path__"):
        path = func.__path__
    # 存储路径
    authenticated_routes.add(path)
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # 查找请求对象
        request = None
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break
        
        if request is None:
            for _, value in kwargs.items():
                if isinstance(value, Request):
                    request = value
                    break
        
        if request is None:
            # 如果找不到请求对象，则直接调用原始函数
            return await func(*args, **kwargs)
        
        # 验证token
        token = request.headers.get('Authorization', '')
        if not token or not token.startswith('Bearer '):
            return JSONResponse(
                {"error": "需要登录", "message": "请登录后再访问此功能"},
                status_code=401
            )
        
        # 验证token有效性
        token = token.replace('Bearer ', '')
        try:
            if AUTH_BASE_URL:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{AUTH_BASE_URL}/api/auth/verify",
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    
                    if response.status_code != 200:
                        return JSONResponse(
                            {"error": "授权无效", "message": "您的登录已过期，请重新登录"},
                            status_code=401
                        )
                    
                    # 将用户信息添加到请求中
                    request.state.user = response.json()
            else:
                # 如果未设置认证URL，则假设认证通过
                request.state.user = {"username": "default_user"}
        except Exception as e:
            return JSONResponse(
                {"error": "验证错误", "message": f"无法验证您的登录状态: {str(e)}"},
                status_code=500
            )
        
        # 通过验证，继续处理请求
        return await func(*args, **kwargs)
    
    # 保存原始路径供中间件使用
    if path.startswith("/"):
        wrapper.__path__ = path
    
    return wrapper

def public(func):
    """
    标记公开路由的装饰器（不需要认证）
    用法: @public
    """
    path = "/" + func.__name__
    # 检查原始函数是否有路径参数
    if hasattr(func, "__path__"):
        path = func.__path__
    # 存储路径
    public_routes.add(path)
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    
    # 保存原始路径供中间件使用
    if path.startswith("/"):
        wrapper.__path__ = path
    
    return wrapper

def set_auth_base_url(url):
    """设置认证基础URL"""
    global AUTH_BASE_URL
    AUTH_BASE_URL = url
    print(f"已设置认证基础URL: {AUTH_BASE_URL}")

def check_path_requires_auth(path):
    """检查路径是否需要认证"""
    # 先检查是否是公开路由
    for route in public_routes:
        if path.startswith(route):
            return False
    
    # 再检查是否是需要认证的路由
    for route in authenticated_routes:
        if path.startswith(route):
            return True
    
    # 默认不需要认证
    return False 