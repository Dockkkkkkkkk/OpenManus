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
        print(f"[DEBUG] 不需要认证，直接放行")
        return {}
    
    # 输出详细的请求信息，帮助调试
    print(f"[DEBUG] 验证请求路径: {request.url.path} 请求方法: {request.method}")
    print(f"[DEBUG] 请求头: {dict(request.headers)}")
    
    # 检查request.state是否已经有认证信息
    if hasattr(request.state, "user") and request.state.user:
        print(f"[DEBUG] 使用request.state中的用户信息: {request.state.user}")
        return request.state.user
    
    # 检查查询参数中是否有用户信息
    user_id = request.query_params.get('user_id')
    username = request.query_params.get('username')
    
    if user_id and username:
        print(f"[DEBUG] 从查询参数中提取到用户信息: user_id={user_id}, username={username}")
        # 创建完整的用户信息对象
        user_info = {
            "id": user_id,
            "user_id": user_id,
            "username": username,
            "is_admin": True,  # 如果有必要，可以从URL参数获取
        }
        # 保存到request.state以供后续使用
        request.state.user = user_info
        return user_info
    
    # 获取token
    token = request.headers.get('Authorization', '')
    auth_token = request.query_params.get('auth_token')
    
    if auth_token and not token:
        token = f"Bearer {auth_token}"
        print(f"[DEBUG] 从查询参数获取到token: {auth_token}")
    
    if not token or not token.startswith('Bearer '):
        print(f"[DEBUG] 没有有效的token: {token}")
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
                # 直接返回完整的用户数据
                user_data = response.json()
                # 确保兼容字段存在
                if "id" not in user_data and "user_id" in user_data:
                    user_data["id"] = user_data["user_id"]
                elif "user_id" not in user_data and "id" in user_data:
                    user_data["user_id"] = user_data["id"]
                
                # 保存到request.state以供后续使用
                request.state.user = user_data
                return user_data
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
            # 输出请求路径和认证状态
            path = request.url.path
            print(f"[DEBUG] 处理请求: {path}, 全局认证: {AUTH_REQUIRED}, 接口认证: {auth_required}")
            
            # 如果全局不需要认证或当前接口不需要认证，直接执行原函数
            if not AUTH_REQUIRED or not auth_required:
                print(f"[DEBUG] 路径 {path} 不需要认证")
                return await func(request, *args, **kwargs)
            
            # 检查URL参数中是否直接提供了用户信息
            user_id = request.query_params.get('user_id')
            username = request.query_params.get('username')
            
            if user_id and username:
                print(f"[DEBUG] 路径 {path} 从URL参数获取到用户信息: user_id={user_id}, username={username}")
                # 创建完整的用户信息对象并设置到request.state
                request.state.user = {
                    "id": user_id,
                    "user_id": user_id,
                    "username": username,
                    "is_admin": True,  # 如果有必要，可以从URL参数获取
                    "avatar": "",
                    "email": "",
                    "roles": []
                }
                # 直接执行原函数，跳过后续验证
                return await func(request, *args, **kwargs)
            
            # 检查URL参数中是否有auth_token
            auth_token = request.query_params.get('auth_token')
            if auth_token:
                # 添加到请求头
                print(f"[DEBUG] 路径 {path} 从URL参数获取到认证令牌: {auth_token}")
                request.headers.__dict__["_list"].append(
                    (b'authorization', f'Bearer {auth_token}'.encode())
                )
            
            # 验证认证信息
            user_info = await verify_auth(request)
            
            if user_info is None:
                # 认证失败，输出详细信息
                print(f"[DEBUG] 路径 {path} 认证失败，token无效或不存在")
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
            print(f"[DEBUG] 路径 {path} 认证成功，用户: {user_info.get('username', '未知')}")
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