import React, { useState, useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";
import authService from "../services/authService";
import { isCognitoEnabled } from "../config/auth";
import { trackLogin, trackLoginFailed } from "../utils/analytics";
import {
  Box,
  Card,
  Flex,
  Text,
  TextField,
  Button,
  Callout,
  Container,
  Heading
} from "@radix-ui/themes";
import { InfoCircledIcon } from "@radix-ui/react-icons";

const Login: React.FC = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const location = useLocation();

  useEffect(() => {
    authService.initializeAuth();
    setIsAuthenticated(authService.isAuthenticated());
  }, []);

  if (isAuthenticated) {
    const from = location.state?.from?.pathname || "/";
    return <Navigate to={from} replace />;
  }

  const returnUrl = location.state?.from?.pathname;

  const handleCognitoLogin = async () => {
    setIsLoading(true);
    await authService.loginWithCognito(returnUrl);
  };

  const handleLegacySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      await authService.loginWithPassword({ username, password });
      trackLogin("password");
      const from = location.state?.from?.pathname || "/";
      window.location.href = from;
    } catch {
      trackLoginFailed("password");
      setError("Invalid username or password");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Container size="1" className="min-h-screen flex items-center justify-center p-4">
      <Card size="4" className="w-full max-w-md">
        <Flex direction="column" gap="4">
          <Box className="text-center">
            <Heading size="6" className="mb-2">
              LIF Metadata Repository
            </Heading>
            <Text size="3" color="gray">
              {isCognitoEnabled
                ? "Sign in or create an account to access the metadata repository"
                : "Sign in to access the metadata repository"}
            </Text>
          </Box>

          {error && (
            <Callout.Root color="red">
              <Callout.Icon>
                <InfoCircledIcon />
              </Callout.Icon>
              <Callout.Text>{error}</Callout.Text>
            </Callout.Root>
          )}

          {isCognitoEnabled ? (
            <Button
              size="3"
              className="w-full"
              disabled={isLoading}
              onClick={handleCognitoLogin}
            >
              {isLoading ? "Redirecting..." : "Sign In / Register"}
            </Button>
          ) : (
            <form onSubmit={handleLegacySubmit}>
              <Flex direction="column" gap="3">
                <Box>
                  <Text size="2" weight="medium" className="block mb-1">
                    Username
                  </Text>
                  <TextField.Root
                    placeholder="Enter your username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                  />
                </Box>

                <Box>
                  <Text size="2" weight="medium" className="block mb-1">
                    Password
                  </Text>
                  <TextField.Root
                    type="password"
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </Box>

                <Button
                  type="submit"
                  size="3"
                  className="w-full"
                  disabled={isLoading}
                >
                  {isLoading ? "Signing in..." : "Sign In"}
                </Button>
              </Flex>
            </form>
          )}
        </Flex>
      </Card>
    </Container>
  );
};

export default Login;
