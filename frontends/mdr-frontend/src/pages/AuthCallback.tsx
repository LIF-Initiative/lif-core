import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Box, Spinner, Flex, Text, Callout, Container } from "@radix-ui/themes";
import { InfoCircledIcon } from "@radix-ui/react-icons";
import authService from "../services/authService";
import { useAuth } from "../context/AuthContext";
import { trackLogin, trackLoginFailed } from "../utils/analytics";

const AuthCallback: React.FC = () => {
  const navigate = useNavigate();
  const { completeLogin } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleAuth = async () => {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      const errorParam = params.get("error");
      const errorDescription = params.get("error_description");

      if (errorParam) {
        trackLoginFailed("cognito");
        setError(errorDescription || errorParam);
        return;
      }

      if (!code) {
        setError("No authorization code received");
        return;
      }

      try {
        const user = await authService.handleCallback(code);
        completeLogin(user);
        trackLogin("cognito");
        // First-login default is /workspaces (lets the user pick which group
        // to enter, or auto-forwards if they have exactly one). A stored
        // returnUrl from a deep-link wins so /invite/accept?token=… etc. still
        // lands where the user clicked.
        //
        // The `autoForwardIfSingle` state flag is only set on this implicit
        // post-auth landing; clicking "Workspaces" in the nav later does not
        // set it, so a single-workspace user can still reach the picker UI
        // (to invite teammates) without being kicked to /explore.
        const stored = authService.getReturnUrl();
        const target = stored === "/" ? "/workspaces" : stored;
        const isWorkspaces = target === "/workspaces";
        navigate(target, {
          replace: true,
          state: isWorkspaces ? { autoForwardIfSingle: true } : undefined,
        });
      } catch (err) {
        trackLoginFailed("cognito");
        setError(err instanceof Error ? err.message : "Authentication failed");
      }
    };

    handleAuth();
  }, [navigate, completeLogin]);

  if (error) {
    return (
      <Container size="1" className="min-h-screen flex items-center justify-center p-4">
        <Box>
          <Callout.Root color="red">
            <Callout.Icon>
              <InfoCircledIcon />
            </Callout.Icon>
            <Callout.Text>
              <Text weight="bold">Authentication failed</Text>
              <br />
              {error}
            </Callout.Text>
          </Callout.Root>
          <Flex justify="center" mt="4">
            <a href="/login">Return to login</a>
          </Flex>
        </Box>
      </Container>
    );
  }

  return (
    <Flex align="center" justify="center" style={{ minHeight: "100vh" }}>
      <Box>
        <Spinner size="3" />
        <Text size="2" color="gray" ml="3">
          Completing sign-in...
        </Text>
      </Box>
    </Flex>
  );
};

export default AuthCallback;
