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
        fileLoading: document.createElement('div') // 创建文件加载指示器元素
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
        }
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
                elements.submit.disabled = false;
                elements.processingIndicator.style.display = 'none';
                appendLog('任务完成', 'system');
                scrollLogsToBottom();
                
                // 切换到文件标签页并显示加载状态
                setTimeout(() => {
                    showFileLoading(true);
                    switchToTab('files-tab');
                    
                    // 每隔1秒检查一次文件生成状态
                    const checkInterval = setInterval(() => {
                        if (generatedFiles.length > 0) {
                            showFileLoading(false);
                            clearInterval(checkInterval);
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