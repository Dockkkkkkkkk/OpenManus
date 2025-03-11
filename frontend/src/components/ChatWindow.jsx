import React, { useEffect, useRef } from 'react';
import ChatMessage from './ChatMessage';

function ChatWindow({ messages }) {
  const messagesEndRef = useRef(null);

  // 自动滚动到最新消息
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="chat-messages">
      {messages.map(message => (
        <ChatMessage 
          key={message.id} 
          type={message.type} 
          content={message.content} 
        />
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
}

export default ChatWindow; 