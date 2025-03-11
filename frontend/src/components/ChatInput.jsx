import React, { useState, useRef, useEffect } from 'react';

function ChatInput({ onSendMessage, isDisabled }) {
  const [input, setInput] = useState('');
  const textareaRef = useRef(null);

  // 自动调整文本区域高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !isDisabled) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleSendMessage = () => {
    if (input.trim() && !isDisabled) {
      onSendMessage(input);
      setInput('');
      
      // 重置文本区域高度
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  return (
    <div className="chat-input-container">
      <div className="chat-input-area">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入您的指令..."
          className="chat-input-textarea"
          disabled={isDisabled}
        />
        <button 
          onClick={handleSendMessage} 
          className="chat-input-button"
          disabled={isDisabled || !input.trim()}
        >
          发送
        </button>
      </div>
    </div>
  );
}

export default ChatInput; 