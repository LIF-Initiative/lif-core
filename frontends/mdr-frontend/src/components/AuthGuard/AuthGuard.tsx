import React, { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Box, Spinner, Flex } from "@radix-ui/themes";
import authService from "@/services/authService";

interface AuthGuardProps {
  children: React.ReactNode;
}

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const checkAuth = () => {
      try {
        // Use authService directly for authentication check
        authService.initializeAuth();
        const authenticated = authService.isAuthenticated();
        setIsAuthenticated(authenticated);
      } catch (error) {
        console.error("Auth check failed:", error);
        setIsAuthenticated(false);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  if (isLoading) {
    return (
      <Flex 
        align="center" 
        justify="center" 
        style={{ minHeight: "100vh" }}
      >
        <Box>
          <Spinner size="3" />
        </Box>
      </Flex>
    );
  }

  if (!isAuthenticated) {
    // Redirect to login page with return url
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

export default AuthGuard;