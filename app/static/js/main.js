document.addEventListener('DOMContentLoaded', () => {
    const prompt = document.getElementById('prompt');
    const submitBtn = document.getElementById('submit');
    const logsContainer = document.getElementById('logs');
    const filesContainer = document.getElementById('files');
    const noFilesMessage = document.getElementById('no-files-message');
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    const processingIndicator = document.getElementById('processing-indicator');
    
    let isProcessing = false;
    let eventSource = null;
    let sentMessageIds = new Set();

    // Tab切换
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.getAttribute('data-target');
            
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(target).classList.add('active');
            
            // 如果切换到文件标签，自动加载文件列表
            if (target === 'files-tab') {
                loadFiles();
            }
        });
    });

    // 提交任务
    submitBtn.addEventListener('click', async () => {
        if (isProcessing) {
            return;
        }
        
        const promptText = prompt.value.trim();
        if (!promptText) {
            return;
        }
        
        isProcessing = true;
        submitBtn.disabled = true;
        processingIndicator.classList.add('active');
        
        // 清空之前的日志和文件列表
        logsContainer.innerHTML = '';
        filesContainer.innerHTML = '';
        noFilesMessage.style.display = 'block';
        
        // 添加用户消息
        appendLog(`用户: ${promptText}`, 'user-message');
        
        // 连接SSE
        connectToEventSource(promptText);
    });

    function connectToEventSource(promptText) {
        if (eventSource) {
            eventSource.close();
        }
        
        sentMessageIds.clear();
        
        // 创建新的EventSource连接
        eventSource = new EventSource(`/api/run?prompt=${encodeURIComponent(promptText)}`);
        
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            // 使用消息ID防止重复显示
            if (!sentMessageIds.has(data.id)) {
                sentMessageIds.add(data.id);
                
                if (data.type === 'log') {
                    let cssClass = 'log-entry';
                    const logText = data.message;
                    
                    if (logText.startsWith('用户:')) {
                        cssClass += ' user-message';
                    } else if (logText.startsWith('系统:')) {
                        cssClass += ' system-message';
                    } else if (logText.toLowerCase().includes('error') || logText.includes('错误')) {
                        cssClass += ' error-message';
                    } else if (logText.startsWith('步骤') || logText.startsWith('Step')) {
                        cssClass += ' step-message';
                    }
                    
                    appendLog(logText, cssClass);
                    
                } else if (data.type === 'file') {
                    console.log("收到文件消息:", data);
                    if (noFilesMessage && noFilesMessage.style.display !== 'none') {
                        noFilesMessage.style.display = 'none';
                    }
                    
                    // 提取文件名
                    let filename = data.filename;
                    if (typeof filename === 'object') {
                        filename = filename.name || filename.path || "未知文件";
                    }
                    
                    appendFile(filename);
                    
                } else if (data.type === 'completion') {
                    appendLog('任务完成', 'system-message');
                    isProcessing = false;
                    submitBtn.disabled = false;
                    processingIndicator.classList.remove('active');
                    
                    if (eventSource) {
                        eventSource.close();
                        eventSource = null;
                    }
                    
                    // 自动切换到文件标签页
                    setTimeout(() => {
                        // 查找文件标签页并激活
                        const fileTab = document.querySelector('.tab[data-target="files-tab"]');
                        if (fileTab) {
                            fileTab.click();
                        }
                        
                        // 刷新文件列表
                        loadFiles();
                    }, 500);
                }
            }
        };
        
        eventSource.onerror = (error) => {
            appendLog('错误: 连接中断', 'error-message');
            isProcessing = false;
            submitBtn.disabled = false;
            processingIndicator.classList.remove('active');
            
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
        };
    }

    function appendLog(message, cssClass = 'log-entry') {
        const entry = document.createElement('div');
        entry.className = cssClass;
        
        // 使用markdown格式化
        const formattedMessage = formatMessage(message);
        entry.innerHTML = formattedMessage;
        
        logsContainer.appendChild(entry);
        logsContainer.scrollTop = logsContainer.scrollHeight;
    }
    
    function appendFile(filename) {
        console.log("appendFile被调用, 文件名:", filename);
        // 如果是对象格式，提取文件名
        if (typeof filename === 'object') {
            filename = filename.name || filename.path || filename.filename || "未知文件";
        }
        
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        
        const fileName = document.createElement('div');
        fileName.className = 'file-name';
        fileName.textContent = filename;
        
        const downloadLink = document.createElement('a');
        downloadLink.className = 'download-link';
        downloadLink.href = `/api/download?filename=${encodeURIComponent(filename)}`;
        downloadLink.textContent = '下载';
        downloadLink.setAttribute('download', '');
        
        fileItem.appendChild(fileName);
        fileItem.appendChild(downloadLink);
        filesContainer.appendChild(fileItem);
        
        // 确保无文件消息被隐藏
        if (noFilesMessage) {
            noFilesMessage.style.display = 'none';
        }
    }
    
    async function loadFiles() {
        try {
            console.log("正在加载文件列表...");
            const response = await fetch('/api/files');
            if (!response.ok) {
                throw new Error(`获取文件列表失败，状态码: ${response.status}`);
            }
            
            const data = await response.json();
            console.log("文件列表数据:", data);
            
            // 清空文件容器
            filesContainer.innerHTML = '';
            
            if (data.files && data.files.length > 0) {
                // 隐藏无文件消息
                if (noFilesMessage) {
                    noFilesMessage.style.display = 'none';
                }
                
                console.log(`显示 ${data.files.length} 个文件`);
                
                // 添加文件项
                data.files.forEach(file => {
                    console.log("添加文件:", file);
                    let filename = file;
                    
                    // 处理可能的对象格式
                    if (typeof file === 'object') {
                        filename = file.name || file.path || "未知文件";
                    }
                    
                    appendFile(filename);
                });
            } else {
                console.log("未找到文件");
                // 显示无文件消息
                filesContainer.innerHTML = '<div class="no-files-message">暂无生成文件</div>';
            }
        } catch (error) {
            console.error('加载文件列表失败:', error);
            filesContainer.innerHTML = `<div class="no-files-message">加载文件列表失败: ${error.message}</div>`;
        }
    }
    
    function formatMessage(message) {
        // 移除制表符前缀
        message = message.replace(/^\s+/, '');
        
        // 代码块处理
        message = message.replace(/```([\s\S]*?)```/g, function(match, code) {
            return `<pre><code>${escapeHtml(code)}</code></pre>`;
        });
        
        // 内联代码处理
        message = message.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        // 保持换行符
        message = message.replace(/\n/g, '<br>');
        
        return message;
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}); 