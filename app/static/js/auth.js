// auth.js - 认证相关功能

// 存储认证状态
const authState = {
    isLoggedIn: false,
    user: null,
    token: null,
    initialized: false
};

// 认证配置
let authConfig = {
    required: false,
    base_url: null,
    client_id: "client1",
    scope: "profile"
};

// 从localStorage加载token
function loadToken() {
    const token = localStorage.getItem('openmanusToken');
    if (token) {
        authState.token = token;
        return token;
    }
    return null;
}

// 保存token到localStorage
function saveToken(token) {
    if (token) {
        localStorage.setItem('openmanusToken', token);
        authState.token = token;
    }
}

// 清除token
function clearToken() {
    localStorage.removeItem('openmanusToken');
    authState.token = null;
    authState.isLoggedIn = false;
    authState.user = null;
}

// 验证token有效性
async function verifyToken() {
    const token = loadToken();
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

// 检查是否需要认证
async function checkAuthRequired() {
    try {
        const response = await fetch('/api/auth/required');
        if (response.ok) {
            const data = await response.json();
            return data.required;
        }
        return false;
    } catch (error) {
        console.error('检查认证需求失败:', error);
        return false;
    }
}

// 获取设备码
async function getDeviceCode() {
    try {
        const response = await fetch('/api/auth/device-code');
        if (response.ok) {
            const data = await response.json();
            // 保存设备码信息到会话，以便后续查询授权状态
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
            throw new Error('获取设备码失败');
        }
    } catch (error) {
        console.error('获取设备码错误:', error);
        throw error;
    }
}

// 轮询授权状态
function startPollingAuth(deviceCode, interval) {
    // 设置轮询间隔（秒）
    const pollInterval = interval || 5;
    
    // 获取保存的设备码数据
    const deviceCodeData = JSON.parse(sessionStorage.getItem('deviceCodeData'));
    if (!deviceCodeData) {
        console.error('无设备码数据，无法轮询授权状态');
        return;
    }
    
    // 计算过期时间
    const expiresAt = deviceCodeData.timestamp + (deviceCodeData.expires_in * 1000);
    
    // 如果已经过期，则停止轮询
    if (Date.now() >= expiresAt) {
        console.log('设备码已过期');
        sessionStorage.removeItem('deviceCodeData');
        return;
    }
    
    // 轮询函数
    const pollAuthStatus = async () => {
        try {
            // 获取客户端ID
            const clientId = authConfig.client_id || 'openmanus';
            console.log(`[DEBUG] 轮询授权状态使用客户端ID: ${clientId}`);
            
            // 调用后端API检查授权状态
            const response = await fetch('/api/auth/token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    device_code: deviceCode,
                    grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
                    client_id: clientId
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                
                if (data.access_token) {
                    // 授权成功，保存token
                    saveToken(data.access_token);
                    
                    // 停止轮询
                    clearTimeout(pollTimer);
                    sessionStorage.removeItem('deviceCodeData');
                    
                    // 验证token并更新用户信息
                    await verifyToken();
                    
                    // 通知登录成功
                    window.dispatchEvent(new CustomEvent('auth:login-success'));
                    
                    // 刷新页面
                    window.location.reload();
                    return;
                }
            } else {
                // 检查错误类型
                const errorData = await response.json();
                
                // 如果是授权中或等待中的错误，继续轮询
                if (errorData.error === 'authorization_pending' || errorData.error === 'slow_down') {
                    // 如果是slow_down错误，增加轮询间隔
                    if (errorData.error === 'slow_down') {
                        pollTimer = setTimeout(pollAuthStatus, (pollInterval + 5) * 1000);
                    } else {
                        pollTimer = setTimeout(pollAuthStatus, pollInterval * 1000);
                    }
                } else {
                    // 其他错误，停止轮询
                    console.error('授权错误:', errorData);
                    sessionStorage.removeItem('deviceCodeData');
                    window.dispatchEvent(new CustomEvent('auth:login-error', { detail: errorData }));
                }
            }
        } catch (error) {
            console.error('轮询授权状态错误:', error);
            // 出错时，继续轮询，除非已经过期
            if (Date.now() < expiresAt) {
                pollTimer = setTimeout(pollAuthStatus, pollInterval * 1000);
            } else {
                sessionStorage.removeItem('deviceCodeData');
            }
        }
    };
    
    // 开始轮询
    let pollTimer = setTimeout(pollAuthStatus, pollInterval * 1000);
}

// 获取认证配置
async function fetchAuthConfig() {
    try {
        console.log('[DEBUG] 获取认证配置...');
        const response = await fetch('/api/auth/config');
        if (response.ok) {
            const config = await response.json();
            console.log('[DEBUG] 获取认证配置成功:', config);
            authConfig = config;
            return config;
        } else {
            console.error('[ERROR] 获取认证配置失败:', response.status);
            return null;
        }
    } catch (error) {
        console.error('[ERROR] 获取认证配置出错:', error);
        return null;
    }
}

// 初始化认证
async function initAuth() {
    // 如果已经初始化，则直接返回
    if (authState.initialized) {
        return authState.isLoggedIn;
    }
    
    // 获取认证配置
    await fetchAuthConfig();
    
    // 标记为已初始化
    authState.initialized = true;
    
    // 首先检查URL参数中是否有token
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('access_token');
    
    if (token) {
        // 保存token并验证
        saveToken(token);
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

// 登出
function logout() {
    clearToken();
    window.location.reload();
}

/**
 * 统一处理API请求，自动处理认证失败
 * @param {string} url - API地址
 * @param {Object} options - fetch选项
 * @returns {Promise<Object>} - 响应数据
 */
async function fetchWithAuth(url, options = {}) {
    // 默认选项
    const defaultOptions = {
        headers: {}
    };

    // 合并选项
    const fetchOptions = { ...defaultOptions, ...options };
    
    // 如果body是FormData，不设置Content-Type，让浏览器自动处理
    if (!(fetchOptions.body instanceof FormData)) {
        fetchOptions.headers = {
            'Content-Type': 'application/json',
            ...fetchOptions.headers
        };
    }
    
    // 如果有token，添加到请求头
    const token = loadToken();
    if (token) {
        fetchOptions.headers = {
            ...fetchOptions.headers,
            'Authorization': `Bearer ${token}`
        };
    }

    try {
        // 发送请求
        const response = await fetch(url, fetchOptions);
        
        // 解析响应
        let data;
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            data = await response.json();
        } else {
            data = await response.text();
        }

        // 如果是401未授权，且有需要登录标记，自动触发登录流程
        if (response.status === 401 && data && data.needs_login) {
            console.log('需要登录，自动触发登录流程');
            // 保存当前URL，登录后返回
            const currentUrl = window.location.href;
            localStorage.setItem('auth_redirect_url', currentUrl);
            
            // 触发登录流程
            await startLoginFlow();
            
            // 登录完成后，返回一个特殊标记，表示正在登录中
            return { _auth_in_progress: true };
        }

        // 返回完整响应
        return {
            ok: response.ok,
            status: response.status,
            data
        };
    } catch (error) {
        console.error('API请求失败:', error);
        throw error;
    }
}

/**
 * 启动登录流程
 * @returns {Promise<void>}
 */
async function startLoginFlow() {
    try {
        console.log('[DEBUG] 开始登录流程...');
        
        // 1. 获取设备码
        console.log('[DEBUG] 正在请求设备码...');
        
        try {
            // 确保已获取最新的认证配置
            if (!authConfig.base_url) {
                console.log('[DEBUG] 在请求设备码前获取最新认证配置');
                await fetchAuthConfig();
            }
            
            console.log(`[DEBUG] 使用认证基础URL: ${authConfig.base_url}`);
            
            // 调用后端 API 获取设备码
            const deviceCodeResponse = await fetch('/api/auth/device-code', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            console.log(`[DEBUG] 设备码响应状态: ${deviceCodeResponse.status}`);
            const responseText = await deviceCodeResponse.text();
            console.log(`[DEBUG] 设备码响应内容: ${responseText}`);
            
            // 尝试将响应解析为JSON
            let deviceCodeData;
            try {
                deviceCodeData = JSON.parse(responseText);
                console.log('[DEBUG] 设备码数据解析成功:', deviceCodeData);
            } catch (jsonError) {
                console.error('[ERROR] 解析设备码响应失败:', jsonError);
                throw new Error(`无法解析设备码响应: ${responseText}`);
            }
            
            if (!deviceCodeResponse.ok) {
                // 详细记录错误信息
                const errorMsg = deviceCodeData.message || deviceCodeData.error || '未知错误';
                console.error('[ERROR] 获取设备码失败:', errorMsg);
                console.error('[ERROR] 设备码请求状态码:', deviceCodeResponse.status);
                
                if (deviceCodeResponse.status === 500) {
                    // 尝试打印完整的错误堆栈，如果有的话
                    if (deviceCodeData.message && deviceCodeData.message.includes('traceback')) {
                        console.error('[ERROR] 服务器错误堆栈:', deviceCodeData.message);
                    }
                    
                    throw new Error(`服务器内部错误(500): ${errorMsg}`);
                }
                
                throw new Error(`获取设备码失败(${deviceCodeResponse.status}): ${errorMsg}`);
            }
            
            // 检查所需字段是否存在
            if (!deviceCodeData.device_code || !deviceCodeData.user_code || !deviceCodeData.verification_uri) {
                console.error('[ERROR] 设备码数据不完整:', deviceCodeData);
                throw new Error('设备码数据不完整或格式不正确');
            }
            
            // 2. 显示登录对话框
            console.log('[DEBUG] 显示登录对话框...');
            showLoginDialog(deviceCodeData);
            
            // 3. 开始轮询token
            console.log('[DEBUG] 开始轮询token...');
            return pollForToken(deviceCodeData);
        } catch (fetchError) {
            console.error('[ERROR] 设备码请求失败:', fetchError);
            throw new Error(`设备码请求失败: ${fetchError.message}`);
        }
    } catch (error) {
        console.error('[ERROR] 启动登录流程失败:', error);
        // 显示一个更友好的错误提示
        const errorDialog = document.createElement('div');
        errorDialog.className = 'login-modal';
        errorDialog.innerHTML = `
            <div class="login-modal-content">
                <h2>登录失败</h2>
                <p>启动登录流程时出错:</p>
                <p class="error-message">${error.message}</p>
                <button id="error-close-btn">关闭</button>
            </div>
        `;
        document.body.appendChild(errorDialog);
        
        // 添加关闭按钮事件
        document.getElementById('error-close-btn').addEventListener('click', function() {
            errorDialog.remove();
        });
        
        throw error;
    }
}

/**
 * 显示登录对话框
 * @param {Object} deviceCodeData - 设备码数据
 */
function showLoginDialog(deviceCodeData) {
    // 创建登录对话框
    const dialogHtml = `
        <div id="login-modal" class="login-modal">
            <div class="login-modal-content">
                <h2>请登录</h2>
                <p>请打开以下网址完成登录:</p>
                <p><a href="${deviceCodeData.verification_uri}" target="_blank">${deviceCodeData.verification_uri}</a></p>
                <p>输入验证码: <strong>${deviceCodeData.user_code}</strong></p>
                <p>或者直接访问: <a href="${deviceCodeData.verification_uri_complete}" target="_blank">${deviceCodeData.verification_uri_complete}</a></p>
                <p>此窗口将在登录完成后自动关闭</p>
                <button id="login-cancel-btn">取消</button>
            </div>
        </div>
    `;
    
    // 添加对话框到页面
    const loginModalDiv = document.createElement('div');
    loginModalDiv.innerHTML = dialogHtml;
    document.body.appendChild(loginModalDiv);
    
    // 添加取消按钮事件
    document.getElementById('login-cancel-btn').addEventListener('click', function() {
        document.getElementById('login-modal').remove();
    });
    
    // 添加简单样式
    const style = document.createElement('style');
    style.textContent = `
        .login-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .login-modal-content {
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            max-width: 500px;
            width: 90%;
        }
        .login-modal-content p {
            margin: 10px 0;
        }
        .login-modal-content button {
            padding: 8px 16px;
            margin-top: 15px;
            cursor: pointer;
        }
    `;
    document.head.appendChild(style);
}

/**
 * 轮询获取token
 * @param {Object} deviceCodeData - 设备码数据
 * @returns {Promise<boolean>} - 是否成功获取token
 */
async function pollForToken(deviceCodeData) {
    const { device_code, interval, expires_in } = deviceCodeData;
    
    // 计算过期时间
    const startTime = Date.now();
    const expiresTime = startTime + (expires_in * 1000);
    
    // 轮询间隔（秒）
    const pollInterval = interval || 5;
    
    // 轮询获取token
    return new Promise((resolve, reject) => {
        const poll = async () => {
            try {
                // 检查是否已过期
                if (Date.now() > expiresTime) {
                    closeLoginDialog();
                    reject(new Error('登录已超时'));
                    return;
                }
                
                // 尝试获取token
                const response = await fetch('/api/auth/token', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        device_code,
                        grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
                        client_id: authConfig.client_id || 'client1'
                    })
                });
                
                const data = await response.json();
                
                // 检查是否获取到token
                if (data.access_token) {
                    // 保存token
                    saveToken(data.access_token);
                    
                    // 关闭登录对话框
                    closeLoginDialog();
                    
                    // 重新加载页面或跳转回原页面
                    const redirectUrl = localStorage.getItem('auth_redirect_url');
                    if (redirectUrl) {
                        localStorage.removeItem('auth_redirect_url');
                        window.location.href = redirectUrl;
                    } else {
                        window.location.reload();
                    }
                    
                    resolve(true);
                    return;
                }
                
                // 如果返回等待中的错误，继续轮询
                if (data.error === 'authorization_pending') {
                    setTimeout(poll, pollInterval * 1000);
                } else if (data.error === 'slow_down') {
                    // 如果要求减慢轮询速度，增加轮询间隔
                    setTimeout(poll, (pollInterval + 5) * 1000);
                } else {
                    // 其他错误，终止轮询
                    closeLoginDialog();
                    reject(new Error(data.error_description || '登录失败'));
                }
            } catch (error) {
                console.error('轮询token失败:', error);
                setTimeout(poll, pollInterval * 1000);
            }
        };
        
        // 开始轮询
        poll();
    });
}

/**
 * 关闭登录对话框
 */
function closeLoginDialog() {
    const loginModal = document.getElementById('login-modal');
    if (loginModal) {
        loginModal.remove();
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

// 导出工具函数
window.Auth = {
    ...(window.Auth || {}),
    fetchWithAuth,
    startLoginFlow,
    showLoginDialog,
    pollForToken,
    closeLoginDialog
}; 