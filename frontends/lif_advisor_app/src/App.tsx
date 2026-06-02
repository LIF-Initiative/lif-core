import { useState, useCallback, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';
import LoginPanel from './components/LoginPanel';
import Banner from './components/Banner';
import axiosInstance from './utils/axios';
import { UserDetails } from './types';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [user, setUser] = useState<UserDetails | null>(null);
  const [isRestoringSession, setIsRestoringSession] = useState(true);

  // Restore an existing session on page load. The stored token is the source of
  // truth: /me returns the current user, and the axios interceptor transparently
  // refreshes an expired access token (or clears it and bounces to login if the
  // refresh token is also dead). No token/profile decoding happens here.
  useEffect(() => {
    let active = true;

    const restoreSession = async () => {
      if (!localStorage.getItem('token')) {
        if (active) setIsRestoringSession(false);
        return;
      }
      try {
        const { data } = await axiosInstance.get<UserDetails>('/me');
        if (!active) return;
        setUser(data);
        setIsLoggedIn(true);
      } catch (err) {
        // Only drop the session on a confirmed auth failure. A transient error
        // (network blip, 5xx) should leave tokens intact so the next load can
        // retry rather than silently logging the user out.
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 401) {
          localStorage.removeItem('token');
          localStorage.removeItem('refreshToken');
        }
      } finally {
        if (active) setIsRestoringSession(false);
      }
    };

    restoreSession();
    return () => {
      active = false;
    };
  }, []);

  const handleLoginSuccess = useCallback((userData: UserDetails) => {
    setUser(userData);
    setIsLoggedIn(true);
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await axiosInstance.post('/logout');
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      localStorage.removeItem('token');
      localStorage.removeItem('refreshToken');
      setUser(null);
      setIsLoggedIn(false);
    }
  }, []);

  // Sample banner content with HTML and links - same as MDR frontend
  const bannerContent = (
    <>
      Need to cite this project? Visit{" "}
      <a 
        href="https://github.com/LIF-Initiative/lif-core" 
        target="_blank" 
        rel="noopener noreferrer"
        className="text-blue-700 underline hover:text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded"
      >
        https://github.com/LIF-Initiative/lif-core
      </a>{" "}
      or click the copy button to grab the citation.
    </>
  );
  // Text to be copied when copy button is clicked
  const copyText = `LIF Initiative. LIF (Learner Information Framework). 2026. GitHub repository: https://github.com/LIF-Initiative/lif-core`;
  const copyRichText = `LIF Initiative. <em>LIF (Learner Information Framework)</em>. 2026.<br/> GitHub repository: <a href="https://github.com/LIF-Initiative/lif-core" target="_blank">https://github.com/LIF-Initiative/lif-core</a>`;

  // Avoid flashing the login screen while we check for an existing session.
  if (isRestoringSession) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div
          className="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600"
          role="status"
          aria-label="Restoring session"
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex flex-col">
      {isLoggedIn && user && (
        <Banner name="citation" content={bannerContent} copyText={copyText} copyRichText={copyRichText} user={user} />
      )}
      <div className="flex items-center justify-center p-0 sm:p-4 md:p-6 lg:p-10 flex-1">
        {isLoggedIn && user ? (
          <div className="w-full max-w-5xl h-[90vh] shadow-2xl rounded-xl overflow-hidden border border-gray-200">
            <ChatInterface key={user.username} onLogout={handleLogout} user={user} />
          </div>
        ) : (
          <LoginPanel onLoginSuccess={handleLoginSuccess} />
        )}
      </div>
    </div>
  );
}

export default App;
