/**
 * 认证工具模块
 * 提供登录、认证检查、安全API请求等功能
 */

// 创建全局Auth对象
window.Auth = (function() {
    // 私有变量
    const TOKEN_KEY = 'auth_token';
    const USER_KEY = 'user';
    
    // 存储认证状态
    const authState = {
        isLoggedIn: false,
        user: null,
        token: null,
        initialized: false
    };
    
    // 检查认证状态
    function isAuthenticated() {
        return !!getToken();
    }
    
    // 获取存储的令牌
    function getToken() {
        // 先尝试从内存中获取
        if (authState.token) {
            return authState.token;
        }
        // 如果内存中没有，从localStorage加载
        return localStorage.getItem(TOKEN_KEY) || '';
    }
    
    // 获取存储的用户信息
    function getUser() {
        try {
            // 先尝试从内存状态获取
            if (authState.user) {
                return authState.user;
            }
            
            const userData = localStorage.getItem(USER_KEY);
            if (userData) {
                const user = JSON.parse(userData);
                authState.user = user;
                return user;
            }
            return null;
        } catch (e) {
            console.error('解析用户信息失败:', e);
            return null;
        }
    }
    
    // 设置认证令牌
    function setToken(token) {
        if (token) {
            localStorage.setItem(TOKEN_KEY, token);
            authState.token = token;
        } else {
            localStorage.removeItem(TOKEN_KEY);
            authState.token = null;
        }
    }
    
    // 设置用户信息
    function setUser(userData) {
        if (userData) {
            localStorage.setItem(USER_KEY, JSON.stringify(userData));
            authState.user = userData;
            authState.isLoggedIn = true;
        } else {
            localStorage.removeItem(USER_KEY);
            authState.user = null;
            authState.isLoggedIn = false;
        }
    }
    
    // 清除认证信息
    function clearToken() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        authState.token = null;
        authState.user = null;
        authState.isLoggedIn = false;
    }
    
    // 刷新登录 - 重定向到登录页面
    function refreshLogin() {
        // 存储当前URL
        const currentUrl = window.location.pathname + window.location.search;
        // 跳转到登录页面
        window.location.href = `/login?redirect=${encodeURIComponent(currentUrl)}`;
    }
    
    // 退出登录
    function logout() {
        clearToken();
        window.location.href = '/';
    }
    
    // 初始化认证
    async function initAuth() {
        // 如果已经初始化，则直接返回
        if (authState.initialized) {
            return authState.isLoggedIn;
        }
        
        // 标记为已初始化
        authState.initialized = true;
        
        // 首先检查URL参数中是否有token
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('access_token');
        
        if (token) {
            // 保存token
            setToken(token);
            // 清除URL中的token参数
            if (window.history && window.history.replaceState) {
                const newUrl = window.location.pathname + window.location.hash;
                window.history.replaceState({}, document.title, newUrl);
            }
        }
        
        // 检查本地存储的token是否有效
        const isValid = await verifyToken();
        return isValid;
    }
    
    // 验证token有效性
    async function verifyToken() {
        const token = getToken();
        if (!token) {
            return false;
        }
    
        try {
            const response = await fetch('/api/auth/verify', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
    
            if (response.ok) {
                const data = await response.json();
                if (data.valid) {
                    authState.isLoggedIn = true;
                    authState.user = data.user;
                    
                    // 将用户信息保存到localStorage，以便在其他地方使用
                    if (data.user) {
                        localStorage.setItem(USER_KEY, JSON.stringify(data.user));
                        console.log('用户信息已保存到localStorage:', data.user);
                    }
                    
                    return true;
                }
            }
            
            // 如果token无效，则清除
            clearToken();
            return false;
        } catch (error) {
            console.error('Token验证失败:', error);
            clearToken();
            return false;
        }
    }
    
    // 获取设备码
    async function getDeviceCode() {
        try {
            console.log('[DEBUG] 开始获取设备码...');
            const response = await fetch('/api/auth/device-code');
            
            if (response.ok) {
                const data = await response.json();
                console.log('[DEBUG] 获取设备码成功:', data);
                
                // 保存设备码信息到会话
                sessionStorage.setItem('deviceCodeData', JSON.stringify({
                    device_code: data.device_code,
                    expires_in: data.expires_in,
                    interval: data.interval,
                    timestamp: Date.now()
                }));
                
                // 开始轮询授权状态
                startPollingAuth(data.device_code, data.interval);
                
                return {
                    user_code: data.user_code,
                    verification_uri: data.verification_uri,
                    expires_in: data.expires_in
                };
            } else {
                console.error('[ERROR] 获取设备码失败:', response.status);
                const errorData = await response.text();
                console.error('[ERROR] 错误详情:', errorData);
                throw new Error(`获取设备码失败: ${response.status}`);
            }
        } catch (error) {
            console.error('[ERROR] 获取设备码出错:', error);
            throw error;
        }
    }
    
    // 轮询授权状态
    function startPollingAuth(deviceCode, interval) {
        // 设置轮询间隔（秒）
        const pollInterval = interval || 5;
        
        // 轮询函数
        const pollAuthStatus = async () => {
            try {
                // 调用后端API检查授权状态
                const response = await fetch('/api/auth/token', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        device_code: deviceCode,
                        grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
                        client_id: 'client1'
                    })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    if (data.access_token) {
                        // 授权成功，保存token
                        setToken(data.access_token);
                        
                        // 验证token并更新用户信息
                        await verifyToken();
                        
                        // 通知登录成功
                        window.dispatchEvent(new CustomEvent('auth:login-success'));
                        
                        // 刷新页面
                        window.location.reload();
                        return;
                    }
                }
                
                // 继续轮询
                setTimeout(pollAuthStatus, pollInterval * 1000);
            } catch (error) {
                console.error('轮询授权状态错误:', error);
                // 出错时，继续轮询
                setTimeout(pollAuthStatus, pollInterval * 1000);
            }
        };
        
        // 开始轮询
        setTimeout(pollAuthStatus, pollInterval * 1000);
    }
    
    // 带认证的Fetch请求
    async function fetchWithAuth(url, options = {}) {
        // 默认设置
        const defaultOptions = {
            method: 'GET',
            headers: {}
        };
        
        // 合并选项
        const fetchOptions = {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...(options.headers || {})
            }
        };
        
        // 如果有认证令牌，添加到请求头
        const token = getToken();
        if (token) {
            fetchOptions.headers['Authorization'] = `Bearer ${token}`;
        }
        
        try {
            // 发送请求
            const response = await fetch(url, fetchOptions);
            
            // 处理401未授权错误
            if (response.status === 401) {
                // 服务器返回JSON响应
                try {
                    const errorData = await response.json();
                    
                    // 检查是否需要登录
                    if (errorData.needs_login) {
                        console.log('需要登录，正在重定向到登录页面');
                        
                        // 标记认证正在进行中
                        const result = {
                            ok: false,
                            status: 401,
                            _auth_in_progress: true,
                            message: '需要登录，正在重定向'
                        };
                        
                        // 触发登录流程
                        setTimeout(() => refreshLogin(), 100);
                        
                        return result;
                    }
                } catch (e) {
                    // 无法解析JSON，可能是其他错误
                    console.error('解析401响应错误:', e);
                }
                
                // 清除过期的令牌
                clearToken();
                
                return {
                    ok: false,
                    status: 401,
                    message: '认证失败'
                };
            }
            
            // 处理其他成功/失败的响应
            let data;
            try {
                data = await response.json();
            } catch (e) {
                data = null;
            }
            
            return {
                ok: response.ok,
                status: response.status,
                data: data
            };
        } catch (error) {
            console.error('请求出错:', error);
            return {
                ok: false,
                status: 0,
                message: error.message
            };
        }
    }
    
    // 导出API
    window.authAPI = {
        initAuth,
        verifyToken,
        getDeviceCode,
        logout,
        getAuthState: () => authState
    };
    
    // 公开API
    return {
        isAuthenticated,
        getToken,
        getUser,
        setToken,
        setUser,
        clearToken,
        refreshLogin,
        logout,
        fetchWithAuth,
        initAuth,
        verifyToken,
        getDeviceCode,
        startPollingAuth
    };
})(); 