import React, { useState, useRef } from 'react';
import axios from 'axios';
import axiosInstance from '../utils/axios';
import { KeyRound, User } from 'lucide-react';
import { UserDetails } from '../types';
import { trackLogin, trackLoginFailed } from '../utils/analytics';

interface LoginPanelProps {
  onLoginSuccess: (user: UserDetails) => void;
}

const LoginPanel: React.FC<LoginPanelProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (isLoading) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    setError('');
    setIsLoading(true);

    abortControllerRef.current = new AbortController();

    try {
      const response = await axiosInstance.post('/login', {
        username,
        password
      }, {
        signal: abortControllerRef.current.signal
      });

      if (response.data.success) {
        localStorage.setItem('token', response.data.access_token);
        localStorage.setItem('refreshToken', response.data.refresh_token);
        trackLogin('password');
        onLoginSuccess(response.data.user);
      }
    } catch (error) {
      if (!axios.isCancel(error)) {
        trackLoginFailed('password');
        setError('Invalid credentials. Please try again.');
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  return (
    <div className="w-full max-w-md bg-white rounded-xl shadow-2xl overflow-hidden">
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-8 py-6 text-white">
        <h2 className="text-2xl font-bold text-center">LIF Advisor</h2>
        <p className="text-blue-100 text-center mt-2">Your personal academic guide</p>
      </div>
      
      <form onSubmit={handleLogin} className="px-8 py-6 space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2" htmlFor="username">
            Username
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <User size={18} className="text-gray-400" />
            </div>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Enter your username"
              name="username"
              id="username"
              required
              disabled={isLoading}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2" htmlFor="password">
            Password
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <KeyRound size={18} className="text-gray-400" />
            </div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Enter your password"
              name="password"
              id="password"
              required
              disabled={isLoading}
            />
          </div>
        </div>

        {error && (
          <div className="text-red-500 text-sm text-center" data-testid="login-error-msg">{error}</div>
        )}

        <button
          type="submit"
          disabled={isLoading}
          className={`w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
            isLoading ? 'opacity-75 cursor-not-allowed' : ''
          }`}
        >
          {isLoading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </div>
  );
};

export default LoginPanel;
