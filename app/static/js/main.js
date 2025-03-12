document.addEventListener('DOMContentLoaded', function() {
    // 选项和元素
    const elements = {
        prompt: document.getElementById('prompt'),
        submit: document.getElementById('submit'),
        logs: document.getElementById('logs'),
        files: document.getElementById('files'),
        processingIndicator: document.getElementById('processing-indicator'),
        tabs: document.querySelectorAll('.tab'),
        tabContents: document.querySelectorAll('.tab-content'),
        noFilesMessage: document.getElementById('no-files-message'),
        fileLoading: document.createElement('div'), // 创建文件加载指示器元素
        goToTasksBtn: document.getElementById('go-to-tasks') // 任务管理按钮
    };
    
    // 初始化文件加载指示器
    elements.fileLoading.className = 'file-loading';
    elements.fileLoading.innerHTML = '<div class="spinner"></div><div>正在提取文件信息...</div>';
    elements.fileLoading.style.display = 'none';
    elements.files.appendChild(elements.fileLoading);
    
    // 初始化事件源
    let eventSource = null;
    
    // 初始化已发送消息ID集合
    const sentMessageIds = new Set();
    
    // 生成的文件列表
    let generatedFiles = [];
    
    // 自动滚动日志到底部
    function scrollLogsToBottom() {
        elements.logs.scrollTop = elements.logs.scrollHeight;
    }
    
    // 切换到指定标签页
    function switchToTab(tabName) {
        // 查找对应的标签页
        const targetTab = Array.from(elements.tabs).find(tab => 
            tab.getAttribute('data-target') === tabName);
        
        if (targetTab) {
            // 移除所有active类
            elements.tabs.forEach(t => t.classList.remove('active'));
            elements.tabContents.forEach(c => c.classList.remove('active'));
            
            // 添加active类到目标tab
            targetTab.classList.add('active');
            document.getElementById(tabName).classList.add('active');
            
            // 如果是任务管理标签，加载iframe
            if (tabName === 'tasks-tab') {
                loadTasksIframe();
            }
        }
    }
    
    /**
     * 加载任务列表
     */
    function loadTasksIframe() {
        // 获取任务容器
        const tasksContainer = document.getElementById('tasks-tab');
        const loadingElement = document.getElementById('tasks-loading');
        
        if (!tasksContainer || !loadingElement) {
            console.error('找不到任务容器或加载状态元素');
            return;
        }
        
        // 显示加载状态
        loadingElement.style.display = 'flex';
        
        // 获取认证信息
        const token = localStorage.getItem('auth_token');
        
        // 如果没有token，显示未登录提示
        if (!token) {
            console.warn('未找到认证令牌，显示登录提示');
            loadingElement.style.display = 'none';
            tasksContainer.innerHTML = `
                <div class="tasks-container">
                    <div class="tasks-unauthorized">
                        <h3>需要登录</h3>
                        <p>请先登录后查看您的任务</p>
                        <button class="login-btn" onclick="window.location.href='/login?redirect=/'">登录</button>
                    </div>
                </div>
            `;
            return;
        }
        
        // 直接调用API获取任务列表
        fetchTasks()
            .then(tasks => {
                // 隐藏加载状态
                loadingElement.style.display = 'none';
                
                // 创建任务列表容器
                const tasksListContainer = document.createElement('div');
                tasksListContainer.className = 'tasks-container';
                
                // 检查是否有任务
                if (!tasks || tasks.length === 0) {
                    tasksListContainer.innerHTML = `
                        <div class="empty-state">
                            <h3>暂无任务</h3>
                            <p>您还没有创建任何任务，请使用上方表单创建任务。</p>
                        </div>
                    `;
                } else {
                    // 创建任务列表
                    const tasksList = document.createElement('div');
                    tasksList.className = 'tasks-list';
                    
                    // 添加表格标题行
                    const headerRow = document.createElement('div');
                    headerRow.className = 'task-header-row';
                    headerRow.innerHTML = `
                        <div class="task-header-cell">任务ID</div>
                        <div class="task-header-cell">创建时间</div>
                        <div class="task-header-cell">状态</div>
                        <div class="task-header-cell">描述</div>
                        <div class="task-header-cell">操作</div>
                    `;
                    tasksList.appendChild(headerRow);
                    
                    // 添加每个任务
                    tasks.forEach(task => {
                        // 任务状态映射
                        const statusMap = {
                            'pending': '等待中',
                            'running': '运行中',
                            'completed': '已完成',
                            'failed': '失败'
                        };
                        
                        // 状态样式映射
                        const statusClassMap = {
                            'pending': 'status-pending',
                            'running': 'status-running',
                            'completed': 'status-completed',
                            'failed': 'status-failed'
                        };
                        
                        // 格式化创建时间
                        const createdAt = task.created_at ? formatDate(task.created_at) : '未知时间';
                        
                        // 创建任务项元素
                        const taskItem = document.createElement('div');
                        taskItem.className = 'task-item';
                        taskItem.innerHTML = `
                            <div class="task-id">${task.id}</div>
                            <div class="task-date">${createdAt}</div>
                            <div class="task-status-container"><span class="task-status ${statusClassMap[task.status] || ''}">${statusMap[task.status] || task.status}</span></div>
                            <div class="task-prompt">${task.prompt || '无描述'}</div>
                            <div class="task-actions">
                                <button class="view-details" data-task-id="${task.id}">查看详情</button>
                            </div>
                        `;
                        
                        // 添加任务详情按钮事件
                        const viewButton = taskItem.querySelector('.view-details');
                        viewButton.addEventListener('click', () => {
                            loadTaskDetail(task.id);
                        });
                        
                        // 添加到任务列表
                        tasksList.appendChild(taskItem);
                    });
                    
                    // 添加任务列表到容器
                    tasksListContainer.appendChild(tasksList);
                }
                
                // 清空并添加任务列表到页面
                tasksContainer.innerHTML = '';
                tasksContainer.appendChild(tasksListContainer);
            })
            .catch(error => {
                console.error('加载任务列表失败:', error);
                loadingElement.style.display = 'none';
                
                tasksContainer.innerHTML = `
                    <div class="error-message">
                        <h3>加载失败</h3>
                        <p>无法加载任务列表: ${error.message}</p>
                        <button class="retry-btn" onclick="loadTasksIframe()">重试</button>
                    </div>
                `;
            });
    }
    
    /**
     * 加载任务详情
     * @param {string|number} taskId - 任务ID
     */
    function loadTaskDetail(taskId) {
        console.log(`加载任务详情: ID=${taskId}`);
        
        // 获取或创建任务容器
        let tasksContainer = document.getElementById('tasks-tab');
        
        // 如果找不到任务容器，尝试创建一个临时容器
        if (!tasksContainer) {
            console.log('找不到tasks-tab容器，尝试查找或创建替代容器');
            // 尝试查找其他可能的容器
            tasksContainer = document.querySelector('.task-container') || document.querySelector('main');
            
            // 如果仍然找不到，创建临时容器并添加到页面
            if (!tasksContainer) {
                console.log('创建临时任务容器');
                tasksContainer = document.createElement('div');
                tasksContainer.id = 'temp-tasks-container';
                tasksContainer.className = 'task-container';
                document.body.appendChild(tasksContainer);
            }
        }
        
        // 创建或获取加载状态元素
        let loadingElement = document.getElementById('tasks-loading');
        if (!loadingElement) {
            console.log('找不到加载状态元素，创建临时加载元素');
            loadingElement = document.createElement('div');
            loadingElement.id = 'tasks-loading';
            loadingElement.className = 'loading-indicator';
            loadingElement.innerHTML = '<div class="spinner"></div><span>正在加载...</span>';
            loadingElement.style.display = 'none';
            tasksContainer.appendChild(loadingElement);
        }
        
        // 显示加载状态
        loadingElement.style.display = 'flex';
        
        // 直接使用fetchWithAuth获取任务详情，避免undefined问题
        fetchWithAuth(`/api/task_detail?task_id=${taskId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`获取任务详情失败: ${response.status}`);
                }
                return response.data;
            })
            .then(task => {
                // 隐藏加载状态
                loadingElement.style.display = 'none';
                
                if (!task) {
                    tasksContainer.innerHTML = `
                        <div class="error-message">
                            <h3>未找到任务</h3>
                            <p>无法找到ID为 ${taskId} 的任务</p>
                            <button class="back-btn" onclick="location.href='/tasks'">返回任务列表</button>
                        </div>
                    `;
                    return;
                }
                
                // 任务状态映射
                const statusMap = {
                    'pending': '等待中',
                    'running': '运行中',
                    'completed': '已完成',
                    'failed': '失败'
                };
                
                // 状态样式映射
                const statusClassMap = {
                    'pending': 'status-pending',
                    'running': 'status-running',
                    'completed': 'status-completed',
                    'failed': 'status-failed'
                };
                
                // 格式化创建和更新时间
                const createdAt = task.created_at ? formatDate(task.created_at) : '未知时间';
                const updatedAt = task.updated_at ? formatDate(task.updated_at) : '未知时间';
                
                // 创建任务详情HTML
                const taskDetailHTML = `
                    <div class="task-detail">
                        <div class="task-detail-header">
                            <button class="back-btn" onclick="location.href='/tasks'">返回任务列表</button>
                            <h2>任务详情</h2>
                        </div>
                        
                        <div class="task-info">
                            <div class="task-info-row">
                                <span class="task-info-label">任务ID:</span>
                                <span class="task-info-value">${task.id}</span>
                            </div>
                            <div class="task-info-row">
                                <span class="task-info-label">状态:</span>
                                <span class="task-info-value ${statusClassMap[task.status] || ''}">${statusMap[task.status] || task.status}</span>
                            </div>
                            <div class="task-info-row">
                                <span class="task-info-label">创建时间:</span>
                                <span class="task-info-value">${createdAt}</span>
                            </div>
                            <div class="task-info-row">
                                <span class="task-info-label">更新时间:</span>
                                <span class="task-info-value">${updatedAt}</span>
                            </div>
                        </div>
                        
                        <div class="task-prompt-section">
                            <h3>任务描述</h3>
                            <div class="task-prompt">${task.prompt || '无描述'}</div>
                        </div>
                        
                        <div class="task-files-section">
                            <h3>生成文件</h3>
                            <div id="task-files-list" class="task-files-list">
                                <div class="loading">正在加载文件列表...</div>
                            </div>
                        </div>
                        
                        <div class="task-logs-section">
                            <h3>执行日志</h3>
                            <div id="task-logs-list" class="task-logs-list">
                                <div class="loading">正在加载日志...</div>
                            </div>
                        </div>
                    </div>
                `;
                
                // 更新页面
                tasksContainer.innerHTML = taskDetailHTML;
                
                // 加载任务文件
                const filesListElement = document.getElementById('task-files-list');
                if (filesListElement) {
                    // 使用POST方法获取文件列表，通过请求体传递参数
                    fetch(`/api/task_detail/files`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ task_id: taskId })
                    })
                        .then(response => {
                            if (!response.ok) {
                                throw new Error(`获取文件列表失败: ${response.status}`);
                            }
                            return response.json();
                        })
                        .then(files => {
                            if (!files || files.length === 0) {
                                filesListElement.innerHTML = '<div class="empty-message">此任务暂无生成文件</div>';
                            } else {
                                // 构建文件列表HTML
                                const filesHtml = files.map(file => `
                                    <div class="file-item">
                                        <div class="file-info">
                                            <div class="file-name">${file.filename}</div>
                                            <div class="file-meta">
                                                <span class="file-size">${formatFileSize(file.size || 0)}</span>
                                                <span class="file-date">${formatDate(file.created_at)}</span>
                                            </div>
                                        </div>
                                        <a href="/api/files/${file.id}/download" class="download-btn" download>下载</a>
                                    </div>
                                `).join('');
                                
                                filesListElement.innerHTML = filesHtml;
                            }
                        })
                        .catch(error => {
                            console.error('获取文件列表失败:', error);
                            filesListElement.innerHTML = '<div class="error-message">获取文件列表失败</div>';
                        });
                }
                
                // 加载任务日志
                const logsListElement = document.getElementById('task-logs-list');
                if (logsListElement) {
                    // 使用POST方法获取任务日志，通过请求体传递参数
                    fetch(`/api/task_detail/logs`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ task_id: taskId })
                    })
                        .then(response => {
                            if (!response.ok) {
                                throw new Error(`获取日志失败: ${response.status}`);
                            }
                            return response.json();
                        })
                        .then(logs => {
                            if (!logs || logs.length === 0) {
                                logsListElement.innerHTML = '<div class="empty-message">此任务暂无执行日志</div>';
                            } else {
                                // 构建日志列表HTML
                                const logsHtml = logs.map(log => `
                                    <div class="log-item log-${log.level || 'info'}">
                                        <div class="log-time">${formatDate(log.timestamp)}</div>
                                        <div class="log-message">${log.message}</div>
                                    </div>
                                `).join('');
                                
                                logsListElement.innerHTML = logsHtml;
                            }
                        })
                        .catch(error => {
                            console.error('获取日志失败:', error);
                            logsListElement.innerHTML = '<div class="error-message">获取日志失败</div>';
                        });
                }
            })
            .catch(error => {
                console.error('加载任务详情失败:', error);
                loadingElement.style.display = 'none';
                
                tasksContainer.innerHTML = `
                    <div class="error-message">
                        <h3>加载失败</h3>
                        <p>无法加载任务详情: ${error.message}</p>
                        <button class="back-btn" onclick="location.href='/tasks'">返回任务列表</button>
                    </div>
                `;
            });
    }
    
    // 显示文件加载中状态
    function showFileLoading(show) {
        elements.fileLoading.style.display = show ? 'flex' : 'none';
        elements.noFilesMessage.style.display = show || generatedFiles.length > 0 ? 'none' : 'block';
    }

    // 创建EventSource，用于接收实时日志更新
    function connectEventSource() {
        // 创建EventSource实例
        eventSource = new EventSource('/api/events');
        
        // 连接打开时
        eventSource.onopen = function() {
            console.log('事件流连接已建立');
        };
        
        // 收到消息时
        eventSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                
                // 避免重复消息
                if (!data.id || !sentMessageIds.has(data.id)) {
                    if (data.id) {
                        sentMessageIds.add(data.id);
                    }
                    handleEvent(data);
                }
            } catch (error) {
                console.error('解析消息出错:', error);
            }
        };
        
        // 发生错误时
        eventSource.onerror = function(error) {
            console.error('事件流错误:', error);
            eventSource.close();
            
            // 10秒后尝试重新连接
            setTimeout(connectEventSource, 10000);
        };
    }
    
    // 处理事件消息
    function handleEvent(data) {
        const eventType = data.type || data.event_type;
        const content = data.message || data.content;
        const files = data.files;
        
        // 处理不同类型的事件
        switch (eventType) {
            case 'log':
                appendLog(content, data.level || 'log');
                scrollLogsToBottom();
                break;
                
            case 'error':
                appendLog(content, 'error');
                scrollLogsToBottom();
                break;
                
            case 'step':
                appendLog(content, 'step');
                scrollLogsToBottom();
                break;
                
            case 'complete':
            case 'task_complete':
            case 'completion':  // 添加新的事件类型以匹配后端
                elements.submit.disabled = false;
                elements.processingIndicator.style.display = 'none';
                appendLog('任务完成', 'system');
                scrollLogsToBottom();
                
                // 切换到文件标签页并显示加载状态
                setTimeout(() => {
                    console.log('任务完成，切换到文件标签页');
                    showFileLoading(true);
                    switchToTab('files-tab');
                    
                    // 立即尝试获取文件列表
                    fetchGeneratedFiles();
                    
                    // 每隔1秒检查一次文件生成状态
                    const checkInterval = setInterval(() => {
                        if (generatedFiles.length > 0) {
                            showFileLoading(false);
                            clearInterval(checkInterval);
                        } else {
                            // 再次尝试获取文件
                            fetchGeneratedFiles();
                        }
                    }, 1000);
                    
                    // 最多等待10秒
                    setTimeout(() => {
                        clearInterval(checkInterval);
                        showFileLoading(false);
                    }, 10000);
                }, 500);
                break;
                
            case 'file':
            case 'generated_files':
                if (files) {
                    updateGeneratedFiles(files);
                    showFileLoading(false);
                } else if (data.filename) {
                    updateGeneratedFiles([data.filename]);
                    showFileLoading(false);
                }
                break;
                
            case 'task_failed':
                elements.submit.disabled = false;
                elements.processingIndicator.style.display = 'none';
                appendLog('任务失败: ' + content, 'error');
                scrollLogsToBottom();
                break;
                
            default:
                console.log('未知事件类型:', eventType);
        }
    }
    
    // 添加日志
    function appendLog(message, type = 'log') {
        // 创建日志条目元素
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry log-${type}`;
        
        // 将消息设置为HTML内容（支持Markdown和代码块格式化）
        logEntry.innerHTML = message;
        
        // 添加到日志容器
        elements.logs.appendChild(logEntry);
        
        // 滚动到底部
        scrollLogsToBottom();
    }
    
    // 更新生成的文件列表
    function updateGeneratedFiles(files) {
        if (!files || files.length === 0) {
            return;
        }
        
        // 更新全局文件列表
        generatedFiles = [...new Set([...generatedFiles, ...files])];
        
        // 清空文件容器
        elements.files.innerHTML = '';
        
        // 隐藏"无文件"消息
        elements.noFilesMessage.style.display = 'none';
        
        // 添加文件加载指示器（但保持隐藏状态）
        elements.files.appendChild(elements.fileLoading);
        
        // 创建文件列表
        const fileList = document.createElement('ul');
        fileList.className = 'file-list';
        
        // 添加每个文件
        generatedFiles.forEach(file => {
            const fileItem = document.createElement('li');
            fileItem.className = 'file-item';
            
            const fileName = document.createElement('span');
            fileName.className = 'file-name';
            fileName.textContent = file;
            
            fileItem.appendChild(fileName);
            fileList.appendChild(fileItem);
            
            // 添加点击事件，打开文件查看对话框
            fileItem.addEventListener('click', function() {
                viewFile(file);
            });
        });
        
        elements.files.appendChild(fileList);
    }
    
    // 查看文件
    function viewFile(filename) {
        // TODO: 实现文件查看功能
        alert('查看文件: ' + filename);
    }
    
    // 添加文件获取函数
    function fetchGeneratedFiles() {
        console.log('获取生成的文件列表');
        
        // 使用fetchWithAuth处理API请求，自动处理认证失败
        window.Auth.fetchWithAuth('/api/files')
            .then(response => {
                if (response.ok && response.data && response.data.files) {
                    console.log('成功获取文件列表:', response.data.files);
                    
                    // 将文件名转换为数组
                    const filenames = response.data.files.map(file => file.name || file.path);
                    
                    // 更新文件列表
                    if (filenames.length > 0) {
                        updateGeneratedFiles(filenames);
                        showFileLoading(false);
                    }
                } else {
                    console.log('获取文件列表失败或为空');
                }
            })
            .catch(error => {
                console.error('获取文件列表出错:', error);
            });
    }
    
    // 监听任务提交事件
    elements.submit.addEventListener('click', async function() {
        const prompt = elements.prompt.value.trim();
        
        if (!prompt) {
            alert('请输入任务描述');
            return;
        }
        
        try {
            // 禁用提交按钮，显示处理指示器
            elements.submit.disabled = true;
            elements.processingIndicator.style.display = 'block';
            
            // 清空日志和文件列表
            elements.logs.innerHTML = '';
            elements.files.innerHTML = '';
            elements.noFilesMessage.style.display = 'block';
            generatedFiles = [];
            sentMessageIds.clear();
            
            // 重新添加文件加载指示器
            elements.files.appendChild(elements.fileLoading);
            
            // 关闭现有的EventSource连接
            if (eventSource) {
                eventSource.close();
            }
            
            // 创建FormData对象
            const formData = new FormData();
            formData.append('prompt', prompt);
            
            // 使用fetchWithAuth处理API请求，自动处理认证失败
            const result = await window.Auth.fetchWithAuth('/api/process', {
                method: 'POST',
                body: formData
            });
            
            // 如果是认证中状态，不继续处理
            if (result._auth_in_progress) {
                console.log('用户正在登录中，暂停处理');
                // 恢复按钮状态
                elements.submit.disabled = false;
                elements.processingIndicator.style.display = 'none';
                return;
            }
            
            // 处理响应
            if (!result.ok) {
                throw new Error(`任务提交失败: ${result.status}`);
            }
            
            // 创建新的EventSource连接
            connectEventSource();
            
            // 切换到日志标签页
            switchToTab('logs-tab');
            
        } catch (error) {
            console.error('任务提交错误:', error);
            alert('提交任务时出错：' + error.message);
            elements.submit.disabled = false;
            elements.processingIndicator.style.display = 'none';
        }
    });
    
    // Tab切换
    elements.tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const target = this.getAttribute('data-target');
            switchToTab(target);
        });
    });
    
    // 初始化连接
    connectEventSource();
});

/**
 * 使用认证信息发送API请求
 * @param {string} url - 请求URL
 * @param {Object} options - 请求选项
 * @returns {Promise<Object>} - 响应对象
 */
async function fetchWithAuth(url, options = {}) {
    // 使用全局Auth对象的fetchWithAuth方法
    if (window.Auth && typeof window.Auth.fetchWithAuth === 'function') {
        return window.Auth.fetchWithAuth(url, options);
    }
    
    // 如果Auth对象不存在，使用简单的实现
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
    
    // 添加认证头
    const token = localStorage.getItem('auth_token');
    if (token) {
        fetchOptions.headers['Authorization'] = `Bearer ${token}`;
    }
    
    try {
        const response = await fetch(url, fetchOptions);
        
        // 处理401错误
        if (response.status === 401) {
            console.error('认证失败，请重新登录');
            
            // 清除过期的认证信息
            localStorage.removeItem('auth_token');
            
            // 重定向到登录页面
            const currentUrl = window.location.pathname + window.location.search;
            window.location.href = `/login?redirect=${encodeURIComponent(currentUrl)}`;
            
            return { ok: false, status: 401, message: '认证已过期' };
        }
        
        // 解析响应数据
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

/**
 * 获取任务列表
 * @returns {Promise<Array>} - 任务列表
 */
async function fetchTasks() {
    const response = await fetchWithAuth('/tasks');
    if (response.ok && Array.isArray(response.data)) {
        return response.data;
    }
    return [];
}

/**
 * 获取任务生成的文件列表
 * @param {string} taskId - 任务ID
 * @returns {Promise<Array>} - 文件列表
 */
async function fetchGeneratedFiles(taskId) {
    try {
        console.log(`正在获取任务 ${taskId} 的生成文件列表...`);
        
        // 显示加载状态
        const fileList = document.getElementById('file-list');
        if (fileList) {
            fileList.innerHTML = '<div class="loading">正在加载文件列表...</div>';
        }
        
        // 使用POST方法和请求体传递任务ID
        const response = await fetchWithAuth(`/api/task_detail/files`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ task_id: taskId })
        });
        
        if (response.ok && Array.isArray(response.data)) {
            console.log(`获取到 ${response.data.length} 个文件`);
            
            // 更新文件列表UI
            if (fileList) {
                if (response.data.length === 0) {
                    fileList.innerHTML = '<div class="empty-message">此任务暂无生成文件</div>';
                } else {
                    // 构建文件列表HTML
                    const filesHtml = response.data.map(file => `
                        <div class="file-item">
                            <div class="file-info">
                                <div class="file-name">${file.filename}</div>
                                <div class="file-meta">
                                    <span class="file-size">${formatFileSize(file.size || 0)}</span>
                                    <span class="file-date">${formatDate(file.created_at)}</span>
                                </div>
                            </div>
                            <a href="/api/files/${file.id}/download" class="download-btn" download>下载</a>
                        </div>
                    `).join('');
                    
                    fileList.innerHTML = filesHtml;
                }
            }
            
            return response.data;
        } else {
            console.error('获取文件列表失败:', response.status, response.message);
            
            if (fileList) {
                fileList.innerHTML = '<div class="error-message">获取文件列表失败</div>';
            }
            
            // 即使请求失败也返回空数组，而不是undefined
            return [];
        }
    } catch (error) {
        console.error('获取文件列表出错:', error);
         
        const fileList = document.getElementById('file-list');
        if (fileList) {
            fileList.innerHTML = '<div class="error-message">获取文件列表时出错</div>';
        }
         
        // 出错时返回空数组而不是undefined
        return [];
    }
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string} - 格式化后的大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * 格式化日期，返回YYYY-MM-DD HH:MM格式
 * @param {string} dateStr - 日期字符串
 * @returns {string} - 格式化后的日期
 */
function formatDate(dateStr) {
    if (!dateStr) return '未知时间';
    
    try {
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return dateStr; // 如果解析失败，返回原始字符串
        
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        
        return `${year}-${month}-${day}<br>${hours}:${minutes}`;
    } catch (e) {
        console.error('日期格式化错误:', e);
        return dateStr;
    }
}

/**
 * 处理事件
 * @param {Object} event - 事件对象
 */
function handleEvent(event) {
    if (!event || !event.type) {
        console.error('收到无效事件:', event);
        return;
    }
    
    console.log(`处理事件: ${event.type}`, event);
    
    const submitBtn = document.getElementById('submit-btn');
    const processingIndicator = document.getElementById('processing-indicator');
    
    switch (event.type) {
        case 'start':
            // 任务开始，禁用提交按钮，显示处理指示器
            if (submitBtn) submitBtn.disabled = true;
            if (processingIndicator) processingIndicator.style.display = 'block';
            break;
            
        case 'progress':
            // 更新处理进度，可以在这里显示百分比等
            if (processingIndicator) {
                processingIndicator.textContent = `处理中... ${event.progress || ''}`;
            }
            break;
            
        case 'error':
            // 错误处理
            if (submitBtn) submitBtn.disabled = false;
            if (processingIndicator) processingIndicator.style.display = 'none';
            
            // 显示错误信息
            showMessage('error', event.message || '处理过程中发生错误');
            break;
            
        case 'completion':
            // 任务完成
            if (submitBtn) submitBtn.disabled = false;
            if (processingIndicator) processingIndicator.style.display = 'none';
            
            // 显示成功信息
            showMessage('success', event.message || '处理已完成');
            
            // 检查是否有任务ID
            if (event.task_id) {
                console.log(`任务 ${event.task_id} 已完成，准备获取生成的文件`);
                
                // 切换到文件标签并显示加载状态
                setTimeout(() => {
                    // 获取文件标签和内容区域
                    const fileTab = document.querySelector('.tab[data-tab="file"]');
                    const fileContent = document.getElementById('file-content');
                    
                    if (fileTab && fileContent) {
                        // 激活文件标签
                        document.querySelectorAll('.tab').forEach(tab => {
                            tab.classList.remove('active');
                        });
                        fileTab.classList.add('active');
                        
                        // 隐藏所有内容区域，显示文件内容区域
                        document.querySelectorAll('.content-area').forEach(content => {
                            content.style.display = 'none';
                        });
                        fileContent.style.display = 'block';
                        
                        // 显示加载状态
                        fileContent.innerHTML = '<div class="loading-container"><div class="loading-spinner"></div><p>正在获取生成的文件...</p></div>';
                        
                        // 获取文件列表
                        setTimeout(() => {
                            fetchGeneratedFiles(event.task_id);
                        }, 500);
                    }
                }, 1000);
            }
            break;
            
        default:
            console.log(`未处理的事件类型: ${event.type}`);
            break;
    }
}

/**
 * 显示消息提示
 * @param {string} type - 消息类型 (success, error, info)
 * @param {string} text - 消息内容
 * @param {number} duration - 显示时间(毫秒)
 */
function showMessage(type, text, duration = 3000) {
    // 创建消息元素
    const messageElement = document.createElement('div');
    messageElement.className = `message message-${type}`;
    messageElement.textContent = text;
    
    // 添加到文档中
    const messageContainer = document.getElementById('message-container');
    if (messageContainer) {
        messageContainer.appendChild(messageElement);
        
        // 添加显示类，触发CSS过渡效果
        setTimeout(() => {
            messageElement.classList.add('show');
        }, 10);
        
        // 设置自动移除
        setTimeout(() => {
            messageElement.classList.remove('show');
            
            // 等待过渡效果结束后移除元素
            setTimeout(() => {
                messageElement.remove();
            }, 300);
        }, duration);
    } else {
        // 如果没有消息容器，直接用alert
        alert(`${type.toUpperCase()}: ${text}`);
    }
} 