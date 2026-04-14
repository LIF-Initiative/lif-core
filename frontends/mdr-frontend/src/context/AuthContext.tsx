import React, { createContext, useContext, useState, useEffect } from "react";
import authService, { UserDetails } from "../services/authService";
import { isCognitoEnabled } from "../config/auth";

interface AuthContextType {
  user: UserDetails | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (returnUrl?: string) => void;
  logout: () => Promise<void>;
  /** True when Cognito is the auth provider, false for legacy password auth */
  isCognito: boolean;
}

interface AuthProviderProps {
  children: React.ReactNode;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<UserDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    authService.initializeAuth();
    const currentUser = authService.getCurrentUser();

    if (authService.isAuthenticated() && currentUser) {
      setUser(currentUser);
    }

    setIsLoading(false);
  }, []);

  const login = (returnUrl?: string): void => {
    if (isCognitoEnabled) {
      authService.loginWithCognito(returnUrl);
    }
    // Legacy login is handled by the Login form directly
  };

  const logout = async (): Promise<void> => {
    await authService.logout();
    setUser(null);
    // For Cognito, logout() redirects to Cognito's logout endpoint.
    // For legacy, the caller (Header) handles the navigate.
  };

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user && authService.isAuthenticated(),
    isLoading,
    login,
    logout,
    isCognito: isCognitoEnabled,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    console.error("useAuth must be used within an AuthProvider");
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
