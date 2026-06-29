import React, { useMemo } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '../types';
import { formatTime, extractOptions } from '../utils/helpers';
import { User, ExternalLink } from 'lucide-react';
import assistantIcon from '../assets/assistant-icon copy.png';

interface MessageItemProps {
  message: Message;
  isTyping?: boolean;
  onOptionClick?: (option: string) => void;
  disabled?: boolean;
}

// Render markdown links as styled buttons that open in a new tab.
const markdownComponents = {
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-0.5 text-blue-700 underline hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {children}
      <ExternalLink size={14} className="shrink-0" />
    </a>
  ),
};

const MessageItem: React.FC<MessageItemProps> = ({ message, isTyping = false, onOptionClick, disabled = false }) => {
  const isBot = message.sender === 'bot';
  // Strip the <<...>> markers from every bot message's displayed text (so history
  // never shows raw markers); option buttons are gated to the active message below.
  const { text: botText, options } = useMemo(
    () => (isBot ? extractOptions(message.content) : { text: message.content, options: [] as string[] }),
    [isBot, message.content]
  );

  return (
    <div 
      className={`flex ${isBot ? 'justify-start' : 'justify-end'} mb-4`}
      style={{ 
        animation: 'fadeIn 0.3s ease-out forwards',
      }}
    >
      <div 
        className={`max-w-[80%] md:max-w-[70%] rounded-2xl px-4 py-3 ${
          isBot 
            ? 'bg-gray-100 text-gray-800 rounded-tl-none' 
            : 'bg-blue-500 text-white rounded-tr-none'
        }`}
        data-testid="message-item"
        data-isbot={isBot}
      >
        <div className="flex items-center gap-2 mb-2">
          <div className={`p-1 rounded-full ${isBot ? 'bg-gray-200' : 'bg-blue-400'}`}>
            {isBot ? (
              <img src={assistantIcon} alt="Assistant" className="w-[20px] h-[20px] object-contain" />
            ) : (
              <User size={16} />
            )}
          </div>
          <span className="text-sm font-medium">{isBot ? <i><strong>LIF</strong>fy</i> : 'You'}</span>
        </div>
        <div className="text-sm md:text-base">
          {isTyping ? (
            <div className="flex space-x-1" data-testid="typing">
              <div className="typing-dot"></div>
              <div className="typing-dot"></div>
              <div className="typing-dot"></div>
            </div>
          ) : (
            <div>
              {isBot ? (
              <article className="prose" data-testid="message-content-bot">
              <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{botText}</Markdown>
              </article>

            ) : (
              <div data-testid="message-content-user">{message.content}</div>
            )}
            </div>
          )}
          {isBot && !isTyping && onOptionClick && options.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2" data-testid="message-options">
              {options.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => onOptionClick(option)}
                  disabled={disabled}
                  data-testid="message-option"
                  className="max-w-full truncate rounded-full border border-blue-300 bg-white px-3 py-1 text-sm text-blue-700 transition-colors hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                  title={option}
                >
                  {option}
                </button>
              ))}
            </div>
          )}
        </div>
        <div 
          className={`text-xs mt-1 flex justify-between items-center ${
            isBot ? 'text-gray-500' : 'text-blue-100'
          }`}
        >
          <span>{formatTime(message.timestamp)}</span>
          {isBot && message.tokens && message.cost && !isTyping && message.tokens > 0 && message.cost > 0 ? (
            <span className="ml-4">
              {message.tokens} tokens (${message.cost.toFixed(6)})
            </span>
          ) : (
            null
          )}
        </div>
      </div>
    </div>
  );
};

export default MessageItem;