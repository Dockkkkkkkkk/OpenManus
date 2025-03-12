from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import httpx
from app.auth import AUTH_REQUIRED, AUTH_BASE_URL, AUTH_CLIENT_ID, AUTH_CLIENT_SECRET, Web

# 创建路由器
router = APIRouter(prefix="/api/auth", tags=["auth"])

# 全局变量
AUTH_SCOPE = "profile"  # 默认认证范围

@router.get('/required')
@Web(auth_required=False)  # 不需要认证
async def auth_required(request: Request):
    """检查是否需要认证才能使用该应用"""
    return JSONResponse({"required": AUTH_REQUIRED})

@router.get('/device-code')
@Web(auth_required=False)  # 不需要认证
async def get_device_code_get(request: Request):
    """获取设备登录码 (GET方法)"""
    result = await _get_device_code()
    # 确保返回正确的响应类型
    if isinstance(result, JSONResponse):
        return result
    return JSONResponse(result)

@router.post('/device-code')
@Web(auth_required=False)  # 不需要认证
async def get_device_code_post(request: Request):
    """获取设备登录码 (POST方法)"""
    result = await _get_device_code()
    # 确保返回正确的响应类型
    if isinstance(result, JSONResponse):
        return result
    return JSONResponse(result)

async def _get_device_code():
    """从用户中心获取设备码"""
    try:
        # 从 auth 模块获取最新的认证配置
        from app.auth import AUTH_BASE_URL, AUTH_CLIENT_ID, AUTH_CLIENT_SECRET
        
        # 格式化认证基础URL，移除末尾的斜杠
        base_url = AUTH_BASE_URL.rstrip('/')
        
        # 详细的调试信息
        print(f"[DEBUG] 认证基础URL: {base_url}")
        print(f"[DEBUG] 完整请求URL: {base_url}/device/code/callback")
        print(f"[DEBUG] 客户端ID: {AUTH_CLIENT_ID}")
        
        # 准备回调URI
        callback_uri = "http://localhost:8000"  # 默认回调地址
        
        # 准备表单数据
        form_data = {
            "client_id": AUTH_CLIENT_ID,
            "callback_uri": callback_uri
        }
        
        # 构建表单数据字符串
        form_str = "&".join([f"{key}={value}" for key, value in form_data.items()])
        
        # 调用用户中心API获取设备码
        async with httpx.AsyncClient(timeout=10.0) as client:  # 增加超时时间
            response = await client.post(
                f"{base_url}/device/code/callback",
                content=form_str,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            
            # 打印完整的响应信息
            print(f"[DEBUG] 设备码响应状态: {response.status_code}")
            try:
                response_data = response.json()
                print(f"[DEBUG] 设备码响应: {response_data}")
            except:
                print(f"[DEBUG] 设备码响应: {response.text}")
                
            # 检查响应状态
            if response.status_code == 200:
                return response.json()
            else:
                # 尝试获取更详细的错误信息
                error_message = "未知错误"
                try:
                    error_data = response.json()
                    error_message = error_data.get("error", "未知错误")
                except Exception as json_err:
                    error_message = f"响应解析失败: {str(json_err)}. 原始响应: {response.text}"
                
                return JSONResponse(
                    {"error": "获取设备码失败", "message": error_message, "status_code": response.status_code},
                    status_code=response.status_code
                )
    except httpx.RequestError as req_err:
        # 捕获网络请求异常
        error_detail = f"请求错误: {type(req_err).__name__}: {str(req_err)}"
        print(f"[ERROR] {error_detail}")
        return JSONResponse(
            {"error": "设备码请求失败", "message": error_detail},
            status_code=500
        )
    except Exception as e:
        # 捕获所有其他异常
        error_detail = f"异常: {type(e).__name__}: {str(e)}"
        print(f"[ERROR] {error_detail}")
        import traceback
        print(f"[ERROR] 详细错误: {traceback.format_exc()}")
        return JSONResponse(
            {"error": "设备码请求处理失败", "message": error_detail},
            status_code=500
        )

@router.post('/token')
@Web(auth_required=False)  # 不需要认证
async def get_token(request: Request):
    """使用设备码获取访问令牌"""
    try:
        # 从 auth 模块获取最新的认证配置
        from app.auth import AUTH_BASE_URL, AUTH_CLIENT_ID, AUTH_CLIENT_SECRET
        
        # 格式化认证基础URL，移除末尾的斜杠
        base_url = AUTH_BASE_URL.rstrip('/')
        
        # 从请求中获取设备码
        data = await request.json()
        device_code = data.get('device_code')
        client_id = data.get('client_id', AUTH_CLIENT_ID)
        
        if not device_code:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "缺少必要的参数"},
                status_code=400
            )
        
        # 准备表单数据
        form_data = f"client_id={client_id}&device_code={device_code}&grant_type=urn:ietf:params:oauth:grant-type:device_code"
        
        # 调用用户中心API获取令牌
        print(f"[DEBUG] 请求令牌: {base_url}/oauth/token")
        print(f"[DEBUG] 表单数据: {form_data}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/oauth/token",
                content=form_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            
            # 打印响应信息
            print(f"[DEBUG] 令牌响应状态: {response.status_code}")
            try:
                print(f"[DEBUG] 令牌响应: {response.json()}")
            except:
                print(f"[DEBUG] 令牌响应: {response.text}")
            
            # 返回用户中心的响应
            status_code = 200 if response.status_code < 500 else response.status_code
            return JSONResponse(
                response.json() if response.status_code == 200 else {"error": "token_error", "error_description": response.text},
                status_code=status_code
            )
    except Exception as e:
        print(f"[ERROR] 获取令牌错误: {str(e)}")
        import traceback
        print(f"[ERROR] 详细错误: {traceback.format_exc()}")
        return JSONResponse(
            {"error": "server_error", "error_description": str(e)},
            status_code=500
        )

@router.get('/verify')
@Web(auth_required=False)  # 不需要认证
async def verify_token(request: Request):
    """验证用户token是否有效"""
    # 从 auth 模块获取最新的认证配置
    from app.auth import AUTH_BASE_URL
    
    # 格式化认证基础URL，移除末尾的斜杠
    base_url = AUTH_BASE_URL.rstrip('/')
    
    # 从请求头获取token
    token = request.headers.get('Authorization', '')
    if not token or not token.startswith('Bearer '):
        return JSONResponse({"valid": False, "message": "缺少有效的token"}, status_code=401)
    
    token = token.replace('Bearer ', '')
    
    try:
        # 调用用户中心API验证token
        print(f"[DEBUG] 验证令牌: {base_url}/verify_token")
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
                return JSONResponse({
                    "valid": True,
                    "user": {
                        "username": user_data.get("username", ""),
                        "avatar": user_data.get("avatar", ""),
                        "email": user_data.get("email", ""),
                        "roles": user_data.get("roles", [])
                    }
                })
            else:
                return JSONResponse({"valid": False, "message": "无效的token"}, status_code=401)
    except Exception as e:
        print(f"[ERROR] 验证令牌错误: {str(e)}")
        import traceback
        print(f"[ERROR] 详细错误: {traceback.format_exc()}")
        return JSONResponse({"valid": False, "message": f"验证失败: {str(e)}"}, status_code=500)

@router.get('/config')
@Web(auth_required=False)  # 不需要认证
async def get_auth_config(request: Request):
    """获取认证配置"""
    from app.auth import AUTH_REQUIRED, AUTH_BASE_URL, AUTH_CLIENT_ID
    
    # 定义默认的认证范围
    auth_scope = "profile"
    
    # 打印当前认证配置信息
    print(f"[DEBUG] 当前认证配置: AUTH_REQUIRED={AUTH_REQUIRED}, AUTH_BASE_URL={AUTH_BASE_URL}")
    
    # 返回认证配置
    return {
        "required": AUTH_REQUIRED,
        "base_url": AUTH_BASE_URL,
        "client_id": AUTH_CLIENT_ID,
        "scope": auth_scope
    } 