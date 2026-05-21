import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Callout,
  Card,
  Container,
  Dialog,
  Flex,
  Heading,
  IconButton,
  Spinner,
  Text,
  TextField,
} from "@radix-ui/themes";
import {
  CheckIcon,
  CopyIcon,
  EnterIcon,
  EnvelopeOpenIcon,
  InfoCircledIcon,
} from "@radix-ui/react-icons";

import tenantsService, {
  CreateInviteResponse,
  WorkspaceItem,
} from "../services/tenantsService";

const AUTO_SELECT_REDIRECT = "/explore";

const Workspaces: React.FC = () => {
  const navigate = useNavigate();

  const [workspaces, setWorkspaces] = useState<WorkspaceItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selecting, setSelecting] = useState<string | null>(null);
  const [selectError, setSelectError] = useState<string | null>(null);

  const [inviteFor, setInviteFor] = useState<string | null>(null);
  const [invitePending, setInvitePending] = useState(false);
  const [invite, setInvite] = useState<CreateInviteResponse | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Load the list once. If the user has exactly one workspace, auto-select
  // and forward to the app — this is the common case for a fresh registrant
  // (post-confirmation lambda just provisioned their personal tenant) and
  // we don't want to make them click a button to pick the only option.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const items = await tenantsService.listMine();
        if (cancelled) return;

        setWorkspaces(items);

        if (items.length === 1) {
          setSelecting(items[0].group);
          try {
            await tenantsService.select(items[0].group);
            if (!cancelled) {
              navigate(AUTO_SELECT_REDIRECT, { replace: true });
            }
          } catch (err) {
            if (!cancelled) {
              setSelecting(null);
              setSelectError(
                err instanceof Error
                  ? err.message
                  : "Could not select your workspace automatically",
              );
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof Error ? err.message : "Failed to load workspaces",
          );
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [navigate]);

  const handleSelect = async (group: string) => {
    setSelecting(group);
    setSelectError(null);
    try {
      await tenantsService.select(group);
      navigate(AUTO_SELECT_REDIRECT, { replace: true });
    } catch (err) {
      setSelecting(null);
      setSelectError(
        err instanceof Error ? err.message : "Failed to select workspace",
      );
    }
  };

  const openInviteFor = (group: string) => {
    setInviteFor(group);
    setInvite(null);
    setInviteError(null);
    setCopied(false);
  };

  const closeInvite = () => {
    setInviteFor(null);
    setInvite(null);
    setInviteError(null);
    setInvitePending(false);
  };

  const generateInvite = async () => {
    if (!inviteFor) return;
    setInvitePending(true);
    setInviteError(null);
    try {
      const result = await tenantsService.createInvite(inviteFor);
      setInvite(result);
    } catch (err) {
      setInviteError(
        err instanceof Error ? err.message : "Failed to create invite",
      );
    } finally {
      setInvitePending(false);
    }
  };

  const inviteUrl = invite
    ? `${window.location.origin}/invite/accept?token=${encodeURIComponent(invite.token)}`
    : "";

  const handleCopy = async () => {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Some browsers block clipboard outside HTTPS / user activation.
      // Fall back: leave the field selectable; user can copy manually.
      setCopied(false);
    }
  };

  // Loading state
  if (workspaces === null && !loadError) {
    return (
      <Container size="2" pt="6">
        <Flex align="center" gap="3" py="6">
          <Spinner size="3" />
          <Text size="2" color="gray">
            Loading your workspaces…
          </Text>
        </Flex>
      </Container>
    );
  }

  return (
    <Container size="2" pt="6" pb="9">
      <Heading size="6" mb="2">
        Your workspaces
      </Heading>
      <Text as="p" size="2" color="gray" mb="5">
        Pick a workspace to open. You can switch any time from this page.
      </Text>

      {loadError && (
        <Callout.Root color="red" mb="4">
          <Callout.Icon>
            <InfoCircledIcon />
          </Callout.Icon>
          <Callout.Text>{loadError}</Callout.Text>
        </Callout.Root>
      )}

      {selectError && (
        <Callout.Root color="red" mb="4">
          <Callout.Icon>
            <InfoCircledIcon />
          </Callout.Icon>
          <Callout.Text>{selectError}</Callout.Text>
        </Callout.Root>
      )}

      {workspaces && workspaces.length === 0 && (
        <Card>
          <Flex direction="column" align="center" gap="2" p="5">
            <Text weight="bold">No workspaces yet</Text>
            <Text size="2" color="gray" align="center">
              You're signed in, but you're not in any group yet. Ask a colleague
              for an invite link, or contact your administrator.
            </Text>
          </Flex>
        </Card>
      )}

      {workspaces && workspaces.length > 0 && (
        <Flex direction="column" gap="3">
          {workspaces.map((ws) => (
            <Card key={ws.group}>
              <Flex align="center" justify="between" gap="3">
                <Box>
                  <Heading size="4">{ws.group}</Heading>
                  <Text size="1" color="gray">
                    Schema: {ws.tenant_schema}
                  </Text>
                </Box>
                <Flex gap="2">
                  <Button
                    variant="soft"
                    onClick={() => openInviteFor(ws.group)}
                  >
                    <EnvelopeOpenIcon /> Invite
                  </Button>
                  <Button
                    onClick={() => handleSelect(ws.group)}
                    disabled={selecting === ws.group}
                  >
                    <EnterIcon />
                    {selecting === ws.group ? "Opening…" : "Open"}
                  </Button>
                </Flex>
              </Flex>
            </Card>
          ))}
        </Flex>
      )}

      <Dialog.Root
        open={inviteFor !== null}
        onOpenChange={(open) => !open && closeInvite()}
      >
        <Dialog.Content style={{ maxWidth: 520 }}>
          <Dialog.Title>Invite someone to "{inviteFor}"</Dialog.Title>
          <Dialog.Description size="2" mb="4">
            Generate a URL to share with someone who already has a Cognito
            account. The link expires after a few days; the recipient is added
            to this workspace's group when they click it.
          </Dialog.Description>

          {inviteError && (
            <Callout.Root color="red" mb="3">
              <Callout.Icon>
                <InfoCircledIcon />
              </Callout.Icon>
              <Callout.Text>{inviteError}</Callout.Text>
            </Callout.Root>
          )}

          {!invite && (
            <Flex justify="end" gap="3">
              <Dialog.Close>
                <Button variant="soft">Cancel</Button>
              </Dialog.Close>
              <Button onClick={generateInvite} disabled={invitePending}>
                {invitePending ? "Generating…" : "Generate invite link"}
              </Button>
            </Flex>
          )}

          {invite && (
            <Box>
              <Text size="2" weight="bold" as="p" mb="2">
                Send this URL to the recipient:
              </Text>
              <Flex gap="2" align="center" mb="3">
                <Box style={{ flex: 1 }}>
                  <TextField.Root value={inviteUrl} readOnly />
                </Box>
                <IconButton onClick={handleCopy} variant="soft" aria-label="Copy invite URL">
                  {copied ? <CheckIcon /> : <CopyIcon />}
                </IconButton>
              </Flex>
              <Text size="1" color="gray" as="p" mb="4">
                Expires {new Date(invite.expires_at * 1000).toLocaleString()}.
              </Text>
              <Flex justify="end">
                <Dialog.Close>
                  <Button variant="soft">Done</Button>
                </Dialog.Close>
              </Flex>
            </Box>
          )}
        </Dialog.Content>
      </Dialog.Root>
    </Container>
  );
};

export default Workspaces;
