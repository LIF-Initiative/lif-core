import React, { useState } from 'react';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import { useChat } from '../hooks/useChat';
import { BarChart3, Search, LogOut } from 'lucide-react';
import { UserDetails } from '../types';
import { trackLogout } from '../utils/analytics';

interface ChatInterfaceProps {
  onLogout: () => void;
  user: UserDetails;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ onLogout, user }) => {
  const { messages, isTyping, isInitializing, sendMessage, displayLoggingOutMessage } = useChat();
  const [loggingOut, setLoggingOut] = useState(false);

  const botMessages = messages.filter(msg => msg.sender === 'bot');
  const totalTokens = botMessages.reduce((sum, msg) => sum + (msg.tokens || 0), 0);
  const totalCost = botMessages.reduce((sum, msg) => sum + (msg.cost || 0), 0);
  const isUserActionsDisabled = isInitializing || isTyping || loggingOut;
  const handleLogout = async () => {
    if (isUserActionsDisabled) return;
    setLoggingOut(true);
    trackLogout();
    displayLoggingOutMessage();
    await onLogout();
  };

  return (
    <div className="flex flex-col bg-white rounded-lg shadow-lg overflow-hidden h-full">
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-4 py-3 flex items-center justify-between">
        <div className="flex items-center">
          <div className="h-12 w-12 rounded-full bg-white/40 p-2 mr-3 flex items-center justify-center">
            <Search size={32} className="text-blue-600" />
          </div>
          <div>
            <h2 className="font-medium text-lg">LIF Advisor</h2>
            <p className="text-sm text-blue-100">
              {user.firstname} {user.lastname} ({user.identifier})
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="bg-white/10 rounded-lg px-3 py-2 flex items-center gap-2">
            <BarChart3 size={16} className="text-blue-100" />
            <div className="text-sm">
              <div className="font-medium">{totalTokens} tokens</div>
              <div className="text-blue-100">${totalCost.toFixed(6)}</div>
            </div>
          </div>

          <button
            onClick={handleLogout}
            disabled={isUserActionsDisabled}
            className={`bg-white/10 hover:bg-white/20 rounded-lg p-2 transition-colors duration-200 ${isUserActionsDisabled ? 'opacity-50 cursor-not-allowed hover:bg-white/10' : ''}`}
            title="Logout"
          >
            <span className="sr-only">Logout</span><LogOut size={20} className="text-white" />
          </button>
        </div>
      </div>

      <MessageList messages={messages} isTyping={isTyping} />

      <MessageInput onSendMessage={sendMessage} disabled={isUserActionsDisabled} />
    </div>
  );
};

export default ChatInterface;
