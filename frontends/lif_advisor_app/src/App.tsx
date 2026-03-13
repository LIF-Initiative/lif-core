import { useState, useCallback, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';
import LoginPanel from './components/LoginPanel';
import Banner from './components/Banner';
import axiosInstance from './utils/axios';
import { UserDetails } from './types';
import { jwtDecode } from 'jwt-decode';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [user, setUser] = useState<UserDetails | null>(null);

  // TODO: Implement proper logic for handling page refresh when authenticated
  // useEffect(() => {
  //   const token = localStorage.getItem('token');
  //   const refreshToken = localStorage.getItem('refreshToken');
  //   const checkToken = async () => {
  //     if (token) {
  //       try {
  //         const decoded = jwtDecode(token);
  //         if (decoded.exp && decoded.exp * 1000 > Date.now()) {
  //           // Token is still valid
  //           setIsLoggedIn(true);
  //           return;
  //         } else if (refreshToken) {
  //           // Token expired, try to refresh
  //           try {
  //             const response = await axiosInstance.post('/refresh-token', { refresh_token: refreshToken });
  //             const { access_token } = response.data;
  //             localStorage.setItem('token', access_token);
  //             setIsLoggedIn(true);
  //             return;
  //           } catch (error) {
  //             localStorage.removeItem('token');
  //             localStorage.removeItem('refreshToken');
  //             setIsLoggedIn(false);
  //             return;
  //           }
  //         } else {
  //           localStorage.removeItem('token');
  //           setIsLoggedIn(false);
  //           return;
  //         }
  //       } catch (error) {
  //         localStorage.removeItem('token');
  //         setIsLoggedIn(false);
  //         return;
  //       }
  //     }
  //     setIsLoggedIn(false);
  //   };
  //   checkToken();
  // }, []);

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
