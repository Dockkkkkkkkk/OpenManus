import React from 'react';
import { marked } from 'marked';
import hljs from 'highlight.js';

// 配置Marked
marked.setOptions({
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true
});

function ChatMessage({ type, content }) {
  return (
    <div className={`message ${type}`}>
      {type === 'user' ? (
        <div>{content}</div>
      ) : (
        <div dangerouslySetInnerHTML={{ __html: marked.parse(content) }} />
      )}
    </div>
  );
}

export default ChatMessage; 