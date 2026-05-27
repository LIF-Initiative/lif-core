import React, { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
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
import { errorToString } from "../utils/errorUtils";

const AUTO_SELECT_REDIRECT = "/explore";

const Workspaces: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  // Only auto-forward on implicit landings (AuthCallback + Home). Explicit
  // navigation to /workspaces from the header nav or "Switch workspace"
  // dropdown leaves this undefined, so a single-workspace user stays on the
  // picker and can reach the Invite button. Read once at mount so a later
  // history.replaceState doesn't change behavior mid-render.
  const autoForwardIfSingle =
    (location.state as { autoForwardIfSingle?: boolean } | null)
      ?.autoForwardIfSingle === true;

  const [workspaces, setWorkspaces] = useState<WorkspaceItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selecting, setSelecting] = useState<string | null>(null);
  const [selectError, setSelectError] = useState<string | null>(null);

  const [inviteFor, setInviteFor] = useState<string | null>(null);
  const [invitePending, setInvitePending] = useState(false);
  const [invite, setInvite] = useState<CreateInviteResponse | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Load the list. On the implicit-landing path (autoForwardIfSingle), a
  // single-workspace user is forwarded straight to /explore — the common
  // case for a fresh registrant whose post-confirmation lambda just
  // provisioned their one tenant. On explicit navigation we always show
  // the picker so the user can reach the Invite button.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const items = await tenantsService.listMine();
        if (cancelled) return;

        setWorkspaces(items);

        if (autoForwardIfSingle && items.length === 1) {
          setSelecting(items[0].group);
          try {
            await tenantsService.select(items[0].group);
            if (!cancelled) {
              navigate(AUTO_SELECT_REDIRECT, { replace: true });
            }
          } catch (err) {
            if (!cancelled) {
              // Don't navigate on auto-select failure — the user would land on
              // /explore with the error invisible. Surface the picker UI
              // instead so they can see what happened and retry manually.
              setSelecting(null);
              setSelectError(errorToString(err));
            }
          }
        }
        // Known trade-off: a fast unmount during auto-select still completes
        // the POST server-side (writing the workspace cookie); the `cancelled`
        // flag only guards setState/navigate, not the in-flight request.
        // Plumbing an AbortController through tenantsService is a follow-up.
      } catch (err) {
        if (!cancelled) {
          setLoadError(errorToString(err));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [autoForwardIfSingle, navigate]);

  const handleSelect = async (group: string) => {
    setSelecting(group);
    setSelectError(null);
    try {
      await tenantsService.select(group);
      navigate(AUTO_SELECT_REDIRECT, { replace: true });
    } catch (err) {
      setSelecting(null);
      setSelectError(errorToString(err));
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
    // Capture the group at call time. If the user closes the dialog or
    // switches workspaces before the response lands, we drop the result
    // instead of showing a token under the wrong dialog title.
    const requestedFor = inviteFor;
    setInvitePending(true);
    setInviteError(null);
    try {
      const result = await tenantsService.createInvite(requestedFor);
      if (inviteForRef.current === requestedFor) {
        setInvite(result);
      }
    } catch (err) {
      if (inviteForRef.current === requestedFor) {
        setInviteError(errorToString(err));
      }
    } finally {
      if (inviteForRef.current === requestedFor) {
        setInvitePending(false);
      }
    }
  };

  // Mirror inviteFor into a ref so the async generateInvite callback can
  // see the *current* dialog target without re-rendering.
  const inviteForRef = useRef<string | null>(inviteFor);
  useEffect(() => {
    inviteForRef.current = inviteFor;
  }, [inviteFor]);

  const inviteUrl = invite
    ? `${window.location.origin}/invite/accept?token=${encodeURIComponent(invite.token)}`
    : "";

  // Track the "copied" reset timeout so we can clear it on unmount or on a
  // re-copy — React warns about setState on unmounted components otherwise.
  const copyResetTimerRef = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (copyResetTimerRef.current !== null) {
        window.clearTimeout(copyResetTimerRef.current);
      }
    },
    [],
  );

  const handleCopy = async () => {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      if (copyResetTimerRef.current !== null) {
        window.clearTimeout(copyResetTimerRef.current);
      }
      copyResetTimerRef.current = window.setTimeout(() => {
        setCopied(false);
        copyResetTimerRef.current = null;
      }, 2000);
    } catch (err) {
      // Some browsers block clipboard outside HTTPS / user activation.
      // Log so we have a breadcrumb if a user reports "copy doesn't work" —
      // the field is still selectable as a manual fallback.
      console.warn("Clipboard copy failed; user can select the URL manually", err);
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
                  {/* display_name is the friendly label (email for personal
                      tenants, group name for shared). Backend guarantees
                      it's present and non-empty — `compute_display_name`
                      falls through to `tenant_schema` rather than ever
                      returning an empty string. Using `||` not `??` so a
                      corrupted runtime value (manual localStorage edit,
                      future code path that writes an empty string) still
                      falls back to `group` rather than rendering a blank
                      heading — defense in depth per Adam Hungerford
                      review of #947. */}
                  <Heading size="4">{ws.display_name || ws.group}</Heading>
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
                    // Disable every Open button while any select is in flight —
                    // not just the one being opened. Otherwise the user can
                    // click Open on a different workspace mid-request and end
                    // up with whichever response wins setting the cookie.
                    disabled={selecting !== null}
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
            account. Each link has a fixed expiry shown below; the recipient is
            added to this workspace's group when they click it.
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
                  <TextField.Root value={inviteUrl} readOnly aria-label="Invite URL" />
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
