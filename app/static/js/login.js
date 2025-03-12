// login.js - 登录UI组件

// 创建登录对话框
function createLoginDialog() {
    // 创建对话框元素
    const dialog = document.createElement('div');
    dialog.className = 'login-dialog';
    dialog.id = 'login-dialog';
    
    // 设置对话框内容
    dialog.innerHTML = `
        <div class="login-dialog-content">
            <div class="login-dialog-header">
                <h3>用户登录</h3>
                <button class="close-button" id="close-login-dialog">×</button>
            </div>
            <div class="login-dialog-body">
                <p>请使用设备码登录系统</p>
                <div class="device-code-container">
                    <div class="user-code" id="user-code">加载中...</div>
                </div>
                <div class="login-actions">
                    <button class="login-button" id="open-login-page">打开登录页面</button>
                </div>
                <div class="login-note">
                    请在打开的页面中输入上面的设备码完成登录
                </div>
                <div class="loading-indicator" id="login-loading">
                    <div class="spinner"></div>
                    <span>获取登录信息中...</span>
                </div>
            </div>
        </div>
    `;
    
    // 添加到页面
    document.body.appendChild(dialog);
    
    // 绑定关闭按钮事件
    document.getElementById('close-login-dialog').addEventListener('click', () => {
        hideLoginDialog();
    });
    
    return dialog;
}

// 显示登录对话框
async function showLoginDialog() {
    // 确保对话框已创建
    let dialog = document.getElementById('login-dialog');
    if (!dialog) {
        dialog = createLoginDialog();
    }
    
    // 显示对话框
    dialog.style.display = 'flex';
    
    // 显示加载状态
    const loadingElement = document.getElementById('login-loading');
    loadingElement.style.display = 'flex';
    
    // 获取设备码
    try {
        const { verification_uri, user_code } = await window.authAPI.getDeviceCode();
        
        // 更新UI
        document.getElementById('user-code').textContent = user_code;
        
        // 绑定登录按钮事件
        const loginButton = document.getElementById('open-login-page');
        loginButton.addEventListener('click', () => {
            window.open(verification_uri, '_self'); // 打开登录页面
        });
        
        // 隐藏加载状态
        loadingElement.style.display = 'none';
    } catch (error) {
        document.getElementById('user-code').textContent = '获取失败';
        loadingElement.style.display = 'none';
        console.error('获取设备码失败:', error);
    }
}

// 隐藏登录对话框
function hideLoginDialog() {
    const dialog = document.getElementById('login-dialog');
    if (dialog) {
        dialog.style.display = 'none';
    }
}

// 创建用户信息栏
function createUserInfoBar(user) {
    const userInfo = document.createElement('div');
    userInfo.className = 'user-info-bar';
    userInfo.id = 'user-info-bar';
    
    // 设置内容
    userInfo.innerHTML = `
        <div class="user-avatar">
            ${user.avatar ? `<img src="${user.avatar}" alt="${user.username}">` : '<div class="avatar-placeholder"></div>'}
        </div>
        <div class="user-name">${user.username}</div>
        <button class="logout-button" id="logout-button">退出</button>
    `;
    
    // 添加到页面
    const header = document.querySelector('.header');
    if (header) {
        header.appendChild(userInfo);
    }
    
    // 绑定退出按钮事件
    document.getElementById('logout-button').addEventListener('click', () => {
        window.authAPI.logout();
    });
    
    return userInfo;
}

// 添加登录按钮
function addLoginButton() {
    const loginButton = document.createElement('button');
    loginButton.className = 'login-button';
    loginButton.id = 'login-button';
    loginButton.textContent = '登录';
    
    // 添加到页面
    const header = document.querySelector('.header');
    if (header) {
        header.appendChild(loginButton);
    }
    
    // 绑定点击事件
    loginButton.addEventListener('click', () => {
        showLoginDialog();
    });
    
    return loginButton;
}

// 初始化登录状态
async function initLoginUI() {
    // 初始化认证状态
    await window.authAPI.initAuth();
    
    // 获取认证状态
    const authState = window.authAPI.getAuthState();
    
    // 根据登录状态更新UI
    if (authState.isLoggedIn && authState.user) {
        // 已登录，显示用户信息
        createUserInfoBar(authState.user);
        
        // 移除登录按钮
        const loginButton = document.getElementById('login-button');
        if (loginButton) {
            loginButton.remove();
        }
    } else {
        // 未登录，显示登录按钮
        addLoginButton();
        
        // 移除用户信息栏
        const userInfoBar = document.getElementById('user-info-bar');
        if (userInfoBar) {
            userInfoBar.remove();
        }
        
        // 检查URL是否有access_token参数
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('access_token')) {
            // 重新初始化认证，处理令牌
            await window.authAPI.initAuth();
            // 刷新页面以应用登录状态
            window.location.reload();
        }
    }
}

// 在页面加载完成后初始化登录UI
document.addEventListener('DOMContentLoaded', () => {
    // 在页面主逻辑初始化后执行登录UI初始化
    setTimeout(initLoginUI, 100);
}); 