import React, { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Box,
  Button,
  Callout,
  Card,
  Container,
  Flex,
  Heading,
  Spinner,
  Text,
} from "@radix-ui/themes";
import {
  CheckCircledIcon,
  CrossCircledIcon,
  ExclamationTriangleIcon,
  InfoCircledIcon,
} from "@radix-ui/react-icons";
import axios from "axios";

import tenantsService, {
  AcceptInviteResponse,
} from "../services/tenantsService";

type Status = "idle" | "accepting" | "success" | "expired" | "invalid" | "error";

const InviteAccept: React.FC = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";

  const [status, setStatus] = useState<Status>("idle");
  const [accepted, setAccepted] = useState<AcceptInviteResponse | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  const handleAccept = async () => {
    if (!token) {
      setStatus("invalid");
      return;
    }
    setStatus("accepting");
    setErrorDetail(null);
    try {
      const result = await tenantsService.acceptInvite(token);
      setAccepted(result);
      setStatus("success");
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const code = err.response?.status;
        const detail = (err.response?.data as { detail?: string } | undefined)?.detail;
        if (code === 410) {
          setStatus("expired");
        } else if (code === 400) {
          setStatus("invalid");
          setErrorDetail(detail ?? null);
        } else {
          setStatus("error");
          setErrorDetail(detail ?? err.message);
        }
      } else {
        setStatus("error");
        setErrorDetail(err instanceof Error ? err.message : String(err));
      }
    }
  };

  // After a successful accept, the recipient's Cognito JWT is stale — the
  // new group isn't reflected until they refresh tokens. Send them through
  // a quick re-login so the next /tenants/mine call surfaces the new group.
  const handleContinue = async () => {
    navigate("/workspaces", { replace: true });
  };

  // No token in URL: misdirected click, expired browser tab, or someone
  // pasted the base URL without the query string.
  if (!token) {
    return (
      <CenteredCard>
        <Flex direction="column" gap="3" align="center">
          <ExclamationTriangleIcon width={32} height={32} color="orange" />
          <Heading size="5">Missing invite token</Heading>
          <Text size="2" color="gray" align="center">
            This URL doesn't include an invite token. Ask the person who
            invited you to send the full link.
          </Text>
        </Flex>
      </CenteredCard>
    );
  }

  if (status === "success" && accepted) {
    return (
      <CenteredCard>
        <Flex direction="column" gap="3" align="center">
          <CheckCircledIcon width={32} height={32} color="green" />
          <Heading size="5">You're in.</Heading>
          <Text size="2" color="gray" align="center">
            You've joined <b>{accepted.group}</b>. The workspace will be
            available the next time you sign in or refresh your session.
          </Text>
          <Button onClick={handleContinue} mt="2">
            Continue to workspaces
          </Button>
        </Flex>
      </CenteredCard>
    );
  }

  if (status === "expired") {
    return (
      <CenteredCard>
        <Flex direction="column" gap="3" align="center">
          <ExclamationTriangleIcon width={32} height={32} color="orange" />
          <Heading size="5">This invite has expired</Heading>
          <Text size="2" color="gray" align="center">
            Invite links are time-limited for security. Ask the person who
            invited you to generate a fresh link.
          </Text>
        </Flex>
      </CenteredCard>
    );
  }

  if (status === "invalid") {
    return (
      <CenteredCard>
        <Flex direction="column" gap="3" align="center">
          <CrossCircledIcon width={32} height={32} color="red" />
          <Heading size="5">Invite link is invalid</Heading>
          <Text size="2" color="gray" align="center">
            We couldn't verify this invite. The link may be malformed or
            tampered with. Ask the sender for a fresh one.
          </Text>
          {errorDetail && (
            <Text size="1" color="gray" align="center" mt="1">
              ({errorDetail})
            </Text>
          )}
        </Flex>
      </CenteredCard>
    );
  }

  if (status === "error") {
    return (
      <CenteredCard>
        <Flex direction="column" gap="3" align="center">
          <CrossCircledIcon width={32} height={32} color="red" />
          <Heading size="5">Something went wrong</Heading>
          <Text size="2" color="gray" align="center">
            We couldn't complete the invite acceptance. Try again, or contact
            support if it keeps happening.
          </Text>
          {errorDetail && (
            <Callout.Root color="gray" size="1" mt="2" style={{ width: "100%" }}>
              <Callout.Icon>
                <InfoCircledIcon />
              </Callout.Icon>
              <Callout.Text>{errorDetail}</Callout.Text>
            </Callout.Root>
          )}
          <Button onClick={handleAccept} mt="2">
            Try again
          </Button>
        </Flex>
      </CenteredCard>
    );
  }

  // status === "idle" or "accepting" — show the confirm UI.
  return (
    <CenteredCard>
      <Flex direction="column" gap="3" align="center">
        <Heading size="5">Accept invite</Heading>
        <Text size="2" color="gray" align="center">
          You've been invited to join a workspace. Click below to add this
          workspace to your account.
        </Text>
        <Button
          onClick={handleAccept}
          disabled={status === "accepting"}
          size="3"
          mt="2"
        >
          {status === "accepting" ? (
            <>
              <Spinner /> Accepting…
            </>
          ) : (
            "Accept invite"
          )}
        </Button>
      </Flex>
    </CenteredCard>
  );
};

const CenteredCard: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Container size="1" pt="9">
    <Flex align="center" justify="center" style={{ minHeight: "70vh" }}>
      <Card style={{ width: "100%", maxWidth: 460 }}>
        <Box p="5">{children}</Box>
      </Card>
    </Flex>
  </Container>
);

export default InviteAccept;
