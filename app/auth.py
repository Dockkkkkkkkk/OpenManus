from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from functools import wraps
import httpx
from typing import Optional, Callable, Any



# 全局认证配置
AUTH_REQUIRED = False
AUTH_BASE_URL = "http://www.dlb.org.cn/auth"
AUTH_CLIENT_ID = "client1"
AUTH_CLIENT_SECRET = ""

# 更新认证配置
def update_auth_config(required: bool, base_url: str, client_id: str, client_secret: str):
    """更新认证配置"""
    global AUTH_REQUIRED, AUTH_BASE_URL, AUTH_CLIENT_ID, AUTH_CLIENT_SECRET
    AUTH_REQUIRED = required
    AUTH_BASE_URL = base_url
    AUTH_CLIENT_ID = client_id
    AUTH_CLIENT_SECRET = client_secret
    print(f"认证配置已更新: 需要认证={AUTH_REQUIRED}, 基础URL={AUTH_BASE_URL}")

# 简单的依赖项函数，用于验证认证
async def verify_auth(request: Request) -> Optional[dict]:
    """验证请求的认证信息，返回用户信息或None"""
    # 如果不需要认证，直接返回空字典
    if not AUTH_REQUIRED:
        return {}
    
    # 获取token
    token = request.headers.get('Authorization', '')
    if not token or not token.startswith('Bearer '):
        return None
    
    token = token.replace('Bearer ', '')
    
    # 验证token
    try:
        # 格式化认证基础URL，移除末尾的斜杠
        base_url = AUTH_BASE_URL.rstrip('/')
        print(f"[DEBUG] 验证token使用URL: {base_url}/verify_token")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/verify_token",
                params={"token": token}
            )
            
            # 打印响应信息
            print(f"[DEBUG] 验证响应状态: {response.status_code}")
            try:
                print(f"[DEBUG] 验证响应: {response.json()}")
            except:
                print(f"[DEBUG] 验证响应: {response.text}")
            
            if response.status_code == 200:
                user_data = response.json()
                return {
                    "username": user_data.get("username", ""),
                    "avatar": user_data.get("avatar", ""),
                    "email": user_data.get("email", ""),
                    "roles": user_data.get("roles", [])
                }
    except Exception as e:
        print(f"验证token时出错: {str(e)}")
        import traceback
        print(f"[ERROR] 详细错误: {traceback.format_exc()}")
    
    return None

# 认证装饰器
def requires_auth(func: Callable) -> Callable:
    """要求认证的装饰器，可以应用于任何需要认证的路由"""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        # 如果不需要认证，直接执行原函数
        if not AUTH_REQUIRED:
            return await func(request, *args, **kwargs)
        
        # 验证认证信息
        user_info = await verify_auth(request)
        
        if user_info is None:
            # 认证失败，返回401错误
            return JSONResponse(
                {"error": "需要登录", "message": "请登录后再访问此功能"},
                status_code=401
            )
        
        # 将用户信息添加到请求状态
        request.state.user = user_info
        
        # 执行原函数
        return await func(request, *args, **kwargs)
    
    return wrapper

# 灵活的Web装饰器 - 可以指定是否需要认证
def Web(auth_required: bool = True):
    """更灵活的Web装饰器，可以指定是否需要认证
    
    用法示例:
    @app.get("/api/public")
    @Web(auth_required=False)
    async def public_route(request: Request):
        return {"message": "这是公开API"}
        
    @app.get("/api/protected")
    @Web(auth_required=True)  # 或者直接 @Web()
    async def protected_route(request: Request):
        # 可以从request.state.user获取用户信息
        user = request.state.user
        return {"message": f"你好，{user.get('username', '用户')}"}
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # 如果全局不需要认证或当前接口不需要认证，直接执行原函数
            if not AUTH_REQUIRED or not auth_required:
                return await func(request, *args, **kwargs)
            
            # 验证认证信息
            user_info = await verify_auth(request)
            
            if user_info is None:
                # 认证失败，返回特殊的JSON响应，包含需要登录的标记
                # 前端可以根据这个标记自动触发登录流程
                return JSONResponse(
                    {
                        "error": "需要登录", 
                        "message": "请登录后再访问此功能",
                        "needs_login": True, 
                        "login_url": f"/login?redirect_url={request.url.path}"
                    },
                    status_code=401
                )
            
            # 将用户信息添加到请求状态
            request.state.user = user_info
            
            # 执行原函数
            return await func(request, *args, **kwargs)
        
        return wrapper
    
    return decorator

# 获取当前用户信息的依赖项
async def get_current_user(request: Request):
    """用于FastAPI依赖注入，获取当前用户信息
    
    用法示例:
    @app.get("/api/user/profile")
    @Web()
    async def get_profile(request: Request, user: dict = Depends(get_current_user)):
        return {"profile": user}
    """
    if hasattr(request.state, "user"):
        return request.state.user
    return None

# 获取用户ID的依赖项
async def get_user_id(request: Request):
    """用于FastAPI依赖注入，获取当前用户ID
    
    用法示例:
    @app.get("/api/user/tasks")
    @Web()
    async def get_tasks(request: Request, user_id: str = Depends(get_user_id)):
        return {"tasks": get_tasks_for_user(user_id)}
    """
    user = await get_current_user(request)
    if user and isinstance(user, dict):
        # 尝试从用户信息中获取ID
        return user.get("id") or user.get("user_id") or user.get("username") or "anonymous"
    return "anonymous"  # 如果无法获取用户ID，则返回匿名ID

# Flask 认证装饰器
def auth_required(f):
    """Flask路由认证装饰器
    
    为了兼容routes.py中使用的Flask装饰器格式
    
    用法示例:
    @app.route('/protected')
    @auth_required
    def protected_route():
        return "这是受保护的路由"
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 如果不需要认证，直接执行原函数
        if not AUTH_REQUIRED:
            return f(*args, **kwargs)
        
        # 这里添加Flask的认证逻辑
        # 由于Flask和FastAPI的请求处理方式不同，这里需要适配
        # 简单处理：如果不需要认证就通过，否则跳转到登录页面
        if not AUTH_REQUIRED:
            return f(*args, **kwargs)
            
        # 这里可以添加更复杂的认证逻辑
        # 例如检查session或cookie中的认证信息
        
        # 如果需要认证但没有通过，可以重定向到登录页面
        from flask import redirect, url_for, request
        return redirect(url_for('login', next=request.url))
        
    return decorated_function 