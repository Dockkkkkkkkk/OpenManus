/**
 * 任务管理模块
 * 提供任务列表、详情查看和文件下载功能
 */
document.addEventListener('DOMContentLoaded', function() {
    // 检查任务管理界面是否存在
    const taskListEl = document.getElementById('task-list');
    const taskDetailEl = document.getElementById('task-detail');
    
    // 如果不存在任务管理相关元素，不初始化此模块
    if (!taskListEl) {
        console.log('任务管理界面未加载，跳过初始化');
        return;
    }
    
    // 任务管理器对象
    const TaskManager = {
        // 当前选中的任务ID
        currentTaskId: null,
        
        // 初始化
        init: function() {
            console.log('初始化任务管理器');
            
            // 创建任务管理界面元素
            this.createTaskUI();
            
            // 加载任务列表
            this.loadTaskList();
            
            // 设置刷新按钮事件
            document.getElementById('refresh-tasks').addEventListener('click', () => {
                this.loadTaskList();
            });
            
            // 任务详情返回按钮事件
            document.getElementById('back-to-tasks').addEventListener('click', () => {
                this.showTaskList();
            });
            
            // 全局事件：当新任务完成时刷新任务列表
            document.addEventListener('task:complete', () => {
                setTimeout(() => this.loadTaskList(), 1000);
            });
        },
        
        // 创建任务管理界面
        createTaskUI: function() {
            // 确保任务管理界面已加载
            if (document.getElementById('task-manager-container')) {
                return;
            }
            
            // 创建任务管理容器
            const container = document.createElement('div');
            container.id = 'task-manager-container';
            container.className = 'task-manager-container';
            
            // 添加任务列表区域
            const taskListArea = document.createElement('div');
            taskListArea.id = 'task-list-area';
            taskListArea.className = 'task-list-area';
            taskListArea.innerHTML = `
                <div class="task-list-header">
                    <h2>我的任务</h2>
                    <button id="refresh-tasks" class="refresh-button">刷新</button>
                </div>
                <div id="task-list" class="task-list"></div>
                <div id="task-list-empty" class="task-list-empty">暂无任务记录</div>
                <div id="task-list-loading" class="task-list-loading">
                    <div class="spinner"></div>
                    <div>加载中...</div>
                </div>
            `;
            
            // 添加任务详情区域
            const taskDetailArea = document.createElement('div');
            taskDetailArea.id = 'task-detail-area';
            taskDetailArea.className = 'task-detail-area hidden';
            taskDetailArea.innerHTML = `
                <div class="task-detail-header">
                    <button id="back-to-tasks" class="back-button">返回</button>
                    <h2 id="task-detail-title">任务详情</h2>
                </div>
                <div id="task-detail" class="task-detail">
                    <div class="task-info">
                        <div class="task-info-row">
                            <span class="task-info-label">任务ID:</span>
                            <span id="task-id" class="task-info-value"></span>
                        </div>
                        <div class="task-info-row">
                            <span class="task-info-label">状态:</span>
                            <span id="task-status" class="task-info-value"></span>
                        </div>
                        <div class="task-info-row">
                            <span class="task-info-label">创建时间:</span>
                            <span id="task-created" class="task-info-value"></span>
                        </div>
                        <div class="task-info-row">
                            <span class="task-info-label">提示词:</span>
                            <div id="task-prompt" class="task-info-value task-prompt"></div>
                        </div>
                    </div>
                    
                    <div class="task-files-section">
                        <h3>生成文件</h3>
                        <div id="task-files" class="task-files">
                            <div id="task-files-empty" class="task-files-empty">暂无生成文件</div>
                        </div>
                    </div>
                    
                    <div class="task-logs-section">
                        <h3>执行日志</h3>
                        <div id="task-logs" class="task-logs"></div>
                    </div>
                </div>
                <div id="task-detail-loading" class="task-detail-loading">
                    <div class="spinner"></div>
                    <div>加载中...</div>
                </div>
            `;
            
            // 添加到页面
            container.appendChild(taskListArea);
            container.appendChild(taskDetailArea);
            
            // 添加到任务管理标签页
            const taskTab = document.getElementById('tasks-tab');
            if (taskTab) {
                taskTab.appendChild(container);
            } else {
                console.error('找不到任务管理标签页，无法添加任务管理界面');
            }
            
            // 添加CSS样式
            this.addTaskManagerStyles();
        },
        
        // 添加任务管理样式
        addTaskManagerStyles: function() {
            // 检查是否已添加样式
            if (document.getElementById('task-manager-styles')) {
                return;
            }
            
            // 创建样式元素
            const style = document.createElement('style');
            style.id = 'task-manager-styles';
            style.textContent = `
                /* 任务管理器容器 */
                .task-manager-container {
                    display: flex;
                    height: 100%;
                    overflow: hidden;
                }
                
                /* 任务列表区域 */
                .task-list-area {
                    width: 300px;
                    border-right: 1px solid #eee;
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                }
                
                .task-list-header {
                    padding: 15px;
                    border-bottom: 1px solid #eee;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                
                .task-list-header h2 {
                    margin: 0;
                    font-size: 18px;
                    font-weight: 500;
                }
                
                .refresh-button {
                    padding: 5px 10px;
                    background: #f0f0f0;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                }
                
                .refresh-button:hover {
                    background: #e0e0e0;
                }
                
                .task-list {
                    flex: 1;
                    overflow-y: auto;
                    padding: 0;
                }
                
                .task-item {
                    padding: 15px;
                    border-bottom: 1px solid #f0f0f0;
                    cursor: pointer;
                    transition: background-color 0.2s;
                }
                
                .task-item:hover {
                    background-color: #f5f5f5;
                }
                
                .task-item.selected {
                    background-color: #e8f0fe;
                    border-left: 3px solid #1a73e8;
                }
                
                .task-item-title {
                    font-weight: 500;
                    margin-bottom: 5px;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                
                .task-item-meta {
                    display: flex;
                    justify-content: space-between;
                    font-size: 12px;
                    color: #666;
                }
                
                .task-status {
                    padding: 2px 6px;
                    border-radius: 10px;
                    font-size: 12px;
                    font-weight: 500;
                }
                
                .task-status-pending {
                    background-color: #fff8e1;
                    color: #ff8f00;
                }
                
                .task-status-running {
                    background-color: #e3f2fd;
                    color: #1976d2;
                }
                
                .task-status-completed {
                    background-color: #e8f5e9;
                    color: #388e3c;
                }
                
                .task-status-failed {
                    background-color: #ffebee;
                    color: #d32f2f;
                }
                
                .task-list-empty, .task-files-empty {
                    display: none;
                    padding: 20px;
                    text-align: center;
                    color: #999;
                    font-style: italic;
                }
                
                .task-list-loading, .task-detail-loading {
                    display: none;
                    padding: 20px;
                    text-align: center;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                }
                
                .spinner {
                    width: 40px;
                    height: 40px;
                    border: 4px solid #f3f3f3;
                    border-top: 4px solid #1a73e8;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin-bottom: 10px;
                }
                
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
                
                /* 任务详情区域 */
                .task-detail-area {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                }
                
                .task-detail-area.hidden {
                    display: none;
                }
                
                .task-detail-header {
                    padding: 15px;
                    border-bottom: 1px solid #eee;
                    display: flex;
                    align-items: center;
                }
                
                .back-button {
                    background: none;
                    border: none;
                    cursor: pointer;
                    padding: 5px 10px;
                    margin-right: 10px;
                    border-radius: 4px;
                }
                
                .back-button:hover {
                    background: #f0f0f0;
                }
                
                .task-detail-header h2 {
                    margin: 0;
                    font-size: 18px;
                    font-weight: 500;
                }
                
                .task-detail {
                    flex: 1;
                    overflow-y: auto;
                    padding: 15px;
                }
                
                .task-info {
                    background-color: #f8f9fa;
                    border-radius: 6px;
                    padding: 15px;
                    margin-bottom: 20px;
                }
                
                .task-info-row {
                    margin-bottom: 10px;
                }
                
                .task-info-label {
                    font-weight: 500;
                    color: #555;
                    margin-right: 10px;
                }
                
                .task-prompt {
                    margin-top: 5px;
                    padding: 10px;
                    background-color: #fff;
                    border-radius: 4px;
                    border: 1px solid #eee;
                    white-space: pre-wrap;
                }
                
                .task-files-section, .task-logs-section {
                    margin-bottom: 20px;
                }
                
                .task-files-section h3, .task-logs-section h3 {
                    font-size: 16px;
                    font-weight: 500;
                    margin-top: 0;
                    padding-bottom: 8px;
                    border-bottom: 1px solid #eee;
                }
                
                .task-file-item {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 10px;
                    border: 1px solid #eee;
                    border-radius: 4px;
                    margin-bottom: 10px;
                    background-color: #fff;
                }
                
                .task-file-info {
                    flex: 1;
                }
                
                .task-file-name {
                    font-weight: 500;
                    margin-bottom: 5px;
                }
                
                .task-file-meta {
                    font-size: 12px;
                    color: #666;
                }
                
                .task-file-download {
                    padding: 5px 10px;
                    background-color: #1a73e8;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                }
                
                .task-file-download:hover {
                    background-color: #1558c2;
                }
                
                .task-logs {
                    padding: 10px;
                    background-color: #f8f9fa;
                    border-radius: 6px;
                    max-height: 400px;
                    overflow-y: auto;
                    font-family: monospace;
                    font-size: 13px;
                    line-height: 1.5;
                    white-space: pre-wrap;
                    word-break: break-word;
                }
            `;
            
            // 添加到文档头部
            document.head.appendChild(style);
        },
        
        // 加载任务列表
        loadTaskList: async function() {
            try {
                // 显示加载状态
                document.getElementById('task-list').style.display = 'none';
                document.getElementById('task-list-empty').style.display = 'none';
                document.getElementById('task-list-loading').style.display = 'flex';
                
                // 使用认证请求获取任务列表
                const response = await window.Auth.fetchWithAuth('/api/tasks/');
                
                // 如果认证进行中，不进行后续处理
                if (response._auth_in_progress) {
                    console.log('正在进行认证，暂停加载任务列表');
                    return;
                }
                
                if (!response.ok) {
                    throw new Error(`获取任务列表失败: ${response.status}`);
                }
                
                const tasks = await response.json();
                
                // 隐藏加载状态
                document.getElementById('task-list-loading').style.display = 'none';
                
                // 显示任务列表或空提示
                if (tasks.length === 0) {
                    document.getElementById('task-list-empty').style.display = 'block';
                    document.getElementById('task-list').style.display = 'none';
                } else {
                    document.getElementById('task-list-empty').style.display = 'none';
                    document.getElementById('task-list').style.display = 'block';
                    
                    // 渲染任务列表
                    this.renderTaskList(tasks);
                }
            } catch (error) {
                console.error('加载任务列表失败:', error);
                document.getElementById('task-list-loading').style.display = 'none';
                document.getElementById('task-list-empty').textContent = `加载失败: ${error.message}`;
                document.getElementById('task-list-empty').style.display = 'block';
                document.getElementById('task-list').style.display = 'none';
            }
        },
        
        // 渲染任务列表
        renderTaskList: function(tasks) {
            const taskListEl = document.getElementById('task-list');
            taskListEl.innerHTML = '';
            
            // 按创建时间降序排序
            tasks.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
            
            // 创建任务列表项
            tasks.forEach(task => {
                const taskItem = document.createElement('div');
                taskItem.className = `task-item ${task.id === this.currentTaskId ? 'selected' : ''}`;
                taskItem.dataset.taskId = task.id;
                
                // 格式化创建时间
                const createdDate = new Date(task.created_at);
                const formattedDate = `${createdDate.getFullYear()}-${String(createdDate.getMonth() + 1).padStart(2, '0')}-${String(createdDate.getDate()).padStart(2, '0')} ${String(createdDate.getHours()).padStart(2, '0')}:${String(createdDate.getMinutes()).padStart(2, '0')}`;
                
                // 截断提示词
                const shortPrompt = task.prompt.length > 40 ? task.prompt.substring(0, 40) + '...' : task.prompt;
                
                taskItem.innerHTML = `
                    <div class="task-item-title">${shortPrompt}</div>
                    <div class="task-item-meta">
                        <span>${formattedDate}</span>
                        <span class="task-status task-status-${task.status}">${this.getStatusText(task.status)}</span>
                    </div>
                `;
                
                // 添加点击事件
                taskItem.addEventListener('click', () => {
                    this.showTaskDetail(task.id);
                });
                
                taskListEl.appendChild(taskItem);
            });
        },
        
        // 获取状态文本
        getStatusText: function(status) {
            const statusMap = {
                'pending': '待处理',
                'running': '执行中',
                'completed': '已完成',
                'failed': '失败'
            };
            return statusMap[status] || status;
        },
        
        // 显示任务详情
        showTaskDetail: async function(taskId) {
            try {
                // 更新当前任务ID
                this.currentTaskId = taskId;
                
                // 更新列表选中状态
                const taskItems = document.querySelectorAll('.task-item');
                taskItems.forEach(item => {
                    if (item.dataset.taskId == taskId) {
                        item.classList.add('selected');
                    } else {
                        item.classList.remove('selected');
                    }
                });
                
                // 显示详情区域，隐藏列表区域（在小屏幕上）
                document.getElementById('task-list-area').classList.add('hidden-xs');
                document.getElementById('task-detail-area').classList.remove('hidden');
                
                // 显示加载状态
                document.getElementById('task-detail').style.display = 'none';
                document.getElementById('task-detail-loading').style.display = 'flex';
                
                // 使用认证请求获取任务详情
                const response = await window.Auth.fetchWithAuth(`/api/tasks/${taskId}`);
                
                // 如果认证进行中，不进行后续处理
                if (response._auth_in_progress) {
                    console.log('正在进行认证，暂停加载任务详情');
                    return;
                }
                
                if (!response.ok) {
                    throw new Error(`获取任务详情失败: ${response.status}`);
                }
                
                const task = await response.json();
                
                // 隐藏加载状态
                document.getElementById('task-detail-loading').style.display = 'none';
                document.getElementById('task-detail').style.display = 'block';
                
                // 渲染任务详情
                this.renderTaskDetail(task);
            } catch (error) {
                console.error('加载任务详情失败:', error);
                document.getElementById('task-detail-loading').style.display = 'none';
                alert(`加载任务详情失败: ${error.message}`);
                this.showTaskList();
            }
        },
        
        // 显示任务列表（返回列表）
        showTaskList: function() {
            // 清空当前任务ID
            this.currentTaskId = null;
            
            // 显示列表区域，隐藏详情区域
            document.getElementById('task-list-area').classList.remove('hidden-xs');
            document.getElementById('task-detail-area').classList.add('hidden');
        },
        
        // 渲染任务详情
        renderTaskDetail: function(task) {
            // 更新任务详情标题
            document.getElementById('task-detail-title').textContent = `任务详情 #${task.id}`;
            
            // 更新任务信息
            document.getElementById('task-id').textContent = task.id;
            document.getElementById('task-status').textContent = this.getStatusText(task.status);
            document.getElementById('task-status').className = `task-info-value task-status task-status-${task.status}`;
            
            // 格式化创建时间
            const createdDate = new Date(task.created_at);
            const formattedDate = `${createdDate.getFullYear()}-${String(createdDate.getMonth() + 1).padStart(2, '0')}-${String(createdDate.getDate()).padStart(2, '0')} ${String(createdDate.getHours()).padStart(2, '0')}:${String(createdDate.getMinutes()).padStart(2, '0')}:${String(createdDate.getSeconds()).padStart(2, '0')}`;
            document.getElementById('task-created').textContent = formattedDate;
            
            // 更新提示词
            document.getElementById('task-prompt').textContent = task.prompt;
            
            // 渲染任务文件
            this.renderTaskFiles(task.files);
            
            // 渲染任务日志
            this.renderTaskLogs(task.logs);
        },
        
        // 渲染任务文件
        renderTaskFiles: function(files) {
            const filesEl = document.getElementById('task-files');
            const filesEmptyEl = document.getElementById('task-files-empty');
            
            // 清空文件列表
            filesEl.innerHTML = '';
            
            // 显示文件列表或空提示
            if (!files || files.length === 0) {
                filesEmptyEl.style.display = 'block';
                return;
            }
            
            filesEmptyEl.style.display = 'none';
            
            // 创建文件列表项
            files.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.className = 'task-file-item';
                
                // 获取文件扩展名
                const ext = file.filename.split('.').pop().toLowerCase();
                
                // 根据扩展名获取文件类型
                const fileType = this.getFileType(ext);
                
                fileItem.innerHTML = `
                    <div class="task-file-info">
                        <div class="task-file-name">${file.filename}</div>
                        <div class="task-file-meta">
                            ${fileType} ${file.file_size ? `· ${this.formatFileSize(file.file_size)}` : ''}
                        </div>
                    </div>
                    <button class="task-file-download" data-file-id="${file.id}">下载</button>
                `;
                
                // 添加下载事件
                const downloadBtn = fileItem.querySelector('.task-file-download');
                downloadBtn.addEventListener('click', () => {
                    this.downloadTaskFile(this.currentTaskId, file.id, file.filename);
                });
                
                filesEl.appendChild(fileItem);
            });
        },
        
        // 获取文件类型
        getFileType: function(extension) {
            const typeMap = {
                // 文本文件
                'txt': '文本文件',
                'md': 'Markdown文档',
                'log': '日志文件',
                
                // 代码文件
                'py': 'Python代码',
                'js': 'JavaScript代码',
                'html': 'HTML文件',
                'css': 'CSS样式表',
                'java': 'Java代码',
                'c': 'C代码',
                'cpp': 'C++代码',
                'h': '头文件',
                'json': 'JSON文件',
                'xml': 'XML文件',
                'yml': 'YAML文件',
                'yaml': 'YAML文件',
                
                // 文档
                'doc': 'Word文档',
                'docx': 'Word文档',
                'pdf': 'PDF文档',
                'ppt': 'PowerPoint演示文稿',
                'pptx': 'PowerPoint演示文稿',
                'xls': 'Excel表格',
                'xlsx': 'Excel表格',
                'csv': 'CSV数据文件',
                
                // 图像
                'jpg': '图像文件',
                'jpeg': '图像文件',
                'png': '图像文件',
                'gif': '图像文件',
                'svg': '矢量图像',
                'webp': '图像文件',
                
                // 压缩文件
                'zip': '压缩文件',
                'rar': '压缩文件',
                'gz': '压缩文件',
                'tar': '归档文件',
                '7z': '压缩文件',
                
                // 音频/视频
                'mp3': '音频文件',
                'wav': '音频文件',
                'mp4': '视频文件',
                'avi': '视频文件',
                'mov': '视频文件'
            };
            
            return typeMap[extension] || '文件';
        },
        
        // 格式化文件大小
        formatFileSize: function(size) {
            if (size < 1024) {
                return `${size} B`;
            } else if (size < 1024 * 1024) {
                return `${(size / 1024).toFixed(1)} KB`;
            } else if (size < 1024 * 1024 * 1024) {
                return `${(size / (1024 * 1024)).toFixed(1)} MB`;
            } else {
                return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
            }
        },
        
        // 渲染任务日志
        renderTaskLogs: function(logs) {
            const logsEl = document.getElementById('task-logs');
            
            // 清空日志
            logsEl.innerHTML = '';
            
            // 如果没有日志，显示提示
            if (!logs) {
                logsEl.textContent = '暂无执行日志';
                return;
            }
            
            // 设置日志内容
            logsEl.textContent = logs;
            
            // 滚动到底部
            logsEl.scrollTop = logsEl.scrollHeight;
        },
        
        // 下载任务文件
        downloadTaskFile: async function(taskId, fileId, filename) {
            try {
                // 显示下载中状态
                const downloadBtn = document.querySelector(`.task-file-download[data-file-id="${fileId}"]`);
                if (downloadBtn) {
                    const originalText = downloadBtn.textContent;
                    downloadBtn.textContent = '下载中...';
                    downloadBtn.disabled = true;
                    
                    try {
                        // 构建下载URL
                        const downloadUrl = `/api/tasks/${taskId}/files/${fileId}/download`;
                        
                        // 使用认证请求获取文件
                        const response = await window.Auth.fetchWithAuth(downloadUrl, {
                            method: 'GET',
                            headers: {
                                'Accept': 'application/octet-stream'
                            }
                        });
                        
                        // 如果认证进行中，不进行后续处理
                        if (response._auth_in_progress) {
                            console.log('正在进行认证，暂停下载文件');
                            return;
                        }
                        
                        if (!response.ok) {
                            throw new Error(`下载文件失败: ${response.status}`);
                        }
                        
                        // 获取文件blob
                        const blob = await response.blob();
                        
                        // 创建下载链接
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.style.display = 'none';
                        a.href = url;
                        a.download = filename;
                        document.body.appendChild(a);
                        
                        // 触发下载
                        a.click();
                        
                        // 清理
                        window.URL.revokeObjectURL(url);
                        document.body.removeChild(a);
                    } finally {
                        // 恢复按钮状态
                        downloadBtn.textContent = originalText;
                        downloadBtn.disabled = false;
                    }
                } else {
                    // 直接下载（如果找不到按钮）
                    window.open(`/api/tasks/${taskId}/files/${fileId}/download`, '_blank');
                }
            } catch (error) {
                console.error('下载文件失败:', error);
                alert(`下载文件失败: ${error.message}`);
            }
        }
    };
    
    // 初始化任务管理器
    TaskManager.init();
    
    // 导出到全局
    window.TaskManager = TaskManager;
}); 