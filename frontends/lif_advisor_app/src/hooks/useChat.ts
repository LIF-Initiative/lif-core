import { useState, useCallback, useEffect } from 'react';
import { Message } from '../types';
import { generateId, delay } from '../utils/helpers';
import axios from 'axios';
import axiosInstance from '../utils/axios';
import { trackEvent } from '../utils/analytics';

export const useChat = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    let isMounted = true;

    const initializeChat = async () => {
      try {
        if (!isMounted) return;

        const initialResponse = await axiosInstance.get('/initial-message', {
          signal: controller.signal
        });

        if (!isMounted) return;

        const initialMessage: Message = {
          id: generateId(),
          content: initialResponse.data.content,
          sender: 'bot',
          timestamp: new Date(),
          tokens: initialResponse.data.tokens,
          cost: initialResponse.data.cost
        };

        setMessages([initialMessage]);

        const typingMessage: Message = {
          id: generateId(),
          content: '',
          sender: 'bot',
          timestamp: new Date()
        };

        setMessages(prev => [...prev, typingMessage]);
        setIsTyping(true);

        await delay(2000);

        if (!isMounted) return;

        const startResponse = await axiosInstance.post('/start-conversation', {}, {
          signal: controller.signal
        });

        if (!isMounted) return;

        const startMessage: Message = {
          id: generateId(),
          content: startResponse.data.content,
          sender: 'bot',
          timestamp: new Date(),
          tokens: startResponse.data.tokens,
          cost: startResponse.data.cost
        };

        setMessages(prev => [...prev.slice(0, -1), startMessage]);
      } catch (error) {
        if (axios.isCancel(error) || !isMounted) return;

        console.error('Failed to initialize chat:', error);
        if (isMounted) {
          const errorMessage: Message = {
            id: generateId(),
            content: "I apologize, but I'm having trouble initializing our conversation. Please try refreshing the page.",
            sender: 'bot',
            timestamp: new Date()
          };
          setMessages([errorMessage]);
        }
      } finally {
        if (isMounted) {
          setIsTyping(false);
          setIsInitializing(false);
          trackEvent('conversation_started');
        }
      }
    };

    initializeChat();

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isInitializing) return;

    const userMessage: Message = {
      id: generateId(),
      content,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    trackEvent('message_sent');

    const typingMessage: Message = {
      id: generateId(),
      content: '',
      sender: 'bot',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, typingMessage]);
    setIsTyping(true);

    const controller = new AbortController();

    try {
      const response = await axiosInstance.post('/continue-conversation', {
        message: content
      }, {
        signal: controller.signal,
        timeout: 0
      });

      const botMessage: Message = {
        id: generateId(),
        content: response.data.content,
        sender: 'bot',
        timestamp: new Date(),
        tokens: response.data.tokens,
        cost: response.data.cost
      };
      console.log(response.data.content)
      // setMessages(prev => [...prev, botMessage]);
      setMessages(prev => [...prev.slice(0, -1), botMessage]);
    } catch (error) {
      if (!axios.isCancel(error)) {
        console.error('Chat error:', error);
        const errorMessage: Message = {
          id: generateId(),
          content: "I apologize, but I'm having trouble processing your message right now. Please try again in a moment.",
          sender: 'bot',
          timestamp: new Date()
        };

        setMessages(prev => [...prev, errorMessage]);
      }
    } finally {
      setIsTyping(false);
    }

    return () => controller.abort();
  }, [isInitializing]);

  const displayLoggingOutMessage = useCallback(() => {
    if (isInitializing || isTyping) return;

    const loggingOutMessage: Message = {
      id: generateId(),
      content: "We are logging you out",
      sender: 'bot',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, loggingOutMessage]);
  }, [isInitializing, isTyping]);

  return { messages, isTyping, isInitializing, sendMessage, displayLoggingOutMessage };
};
