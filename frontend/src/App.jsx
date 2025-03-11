import React, { useState, useEffect } from 'react';
import ChatInput from './components/ChatInput';
import ChatMessage from './components/ChatMessage';

function App() {
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // 连接到SSE日志流
    const eventSource = new EventSource('/api/logs');

    eventSource.addEventListener('connect', (event) => {
      console.log('连接已建立');
      setIsConnected(true);
      
      // 添加系统消息
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'system',
        content: '已连接到OpenManus系统'
      }]);
    });

    eventSource.addEventListener('log', (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.content) {
          // 添加AI消息
          setMessages(prev => [...prev, {
            id: Date.now(),
            type: 'ai',
            content: data.content
          }]);
        }
      } catch (error) {
        console.error('解析消息失败:', error);
      }
    });

    eventSource.onerror = () => {
      console.error('SSE连接错误');
      setIsConnected(false);
      
      // 添加错误消息
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'system',
        content: '连接已断开，尝试重新连接...'
      }]);
    };

    return () => {
      eventSource.close();
    };
  }, []);

  const sendMessage = async (content) => {
    if (!content.trim()) return;

    // 添加用户消息
    setMessages(prev => [...prev, {
      id: Date.now(),
      type: 'user',
      content
    }]);

    try {
      // 发送消息到后端
      const response = await fetch('/api/prompt', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ prompt: content })
      });

      if (!response.ok) {
        throw new Error('请求失败');
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      
      // 添加错误消息
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'system',
        content: `发送消息失败: ${error.message}`
      }]);
    }
  };

  return (
    <div className="app-container">
      <div className="app-header">
        <h1>OpenManus AI助手</h1>
        <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
          {isConnected ? '已连接' : '已断开'}
        </div>
      </div>
      
      <div className="app-content">
        {/* 左侧输入区域 */}
        <div className="input-panel">
          <h2>命令输入</h2>
          <ChatInput onSendMessage={sendMessage} isDisabled={!isConnected} />
          <div className="input-instructions">
            <h3>使用说明</h3>
            <ul>
              <li>在上方输入框中输入命令</li>
              <li>按Enter或点击发送按钮提交</li>
              <li>系统响应将显示在右侧日志区域</li>
            </ul>
          </div>
        </div>
        
        {/* 右侧日志区域 */}
        <div className="log-panel">
          <h2>系统日志</h2>
          <div className="log-container">
            {messages.map(message => (
              <ChatMessage 
                key={message.id} 
                type={message.type} 
                content={message.content} 
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App; 