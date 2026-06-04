import React, { useRef, useEffect } from 'react';
import { Message } from '../types';
import MessageItem from './MessageItem';

interface MessageListProps {
  messages: Message[];
  isTyping: boolean;
  onOptionClick?: (option: string) => void;
  optionsDisabled?: boolean;
}

const MessageList: React.FC<MessageListProps> = ({ messages, isTyping, onOptionClick, optionsDisabled }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {messages.map((message, index) => (
        <MessageItem
          key={message.id}
          message={message}
          isTyping={isTyping && index === messages.length - 1 && message.sender === 'bot'}
          onOptionClick={index === messages.length - 1 ? onOptionClick : undefined}
          disabled={optionsDisabled}
        />
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList