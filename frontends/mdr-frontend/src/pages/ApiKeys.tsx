import { useEffect, useRef, useState } from "react";
import {
  AlertDialog,
  Badge,
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
import { CheckIcon, CopyIcon, InfoCircledIcon, PlusIcon, TrashIcon } from "@radix-ui/react-icons";
import apiKeysService, { ApiKey, CreateApiKeyResponse } from "../services/apiKeysService";
import { useToast } from "../context/ToastContext";
import { errorToString } from "../utils/errorUtils";

const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : "—");

export default function ApiKeys() {
  const { showToast } = useToast();

  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [loadError, setLoadError] = useState<string>("");

  // Create dialog.
  const [createOpen, setCreateOpen] = useState(false);
  const [label, setLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<CreateApiKeyResponse | null>(null); // holds the raw key, shown once
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Revoke.
  const [revokingId, setRevokingId] = useState<number | null>(null);

  const load = async () => {
    try {
      const items = await apiKeysService.listApiKeys();
      setKeys(items);
      setLoadError("");
    } catch (err) {
      setLoadError(errorToString(err));
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const items = await apiKeysService.listApiKeys();
        if (!cancelled) setKeys(items);
      } catch (err) {
        if (!cancelled) setLoadError(errorToString(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(
    () => () => {
      if (copyTimer.current) clearTimeout(copyTimer.current);
    },
    [],
  );

  const openCreate = () => {
    setLabel("");
    setCreated(null);
    setCopied(false);
    setCreateOpen(true);
  };
  const closeCreate = () => {
    setCreateOpen(false);
    setCreated(null);
    setLabel("");
    setCopied(false);
  };

  const handleCreate = async () => {
    if (!label.trim()) return;
    setCreating(true);
    try {
      const resp = await apiKeysService.createApiKey(label.trim());
      setCreated(resp);
      showToast("API key created — copy it now, it won't be shown again", "warning");
      await load();
    } catch (err) {
      showToast(errorToString(err), "error");
    } finally {
      setCreating(false);
    }
  };

  const handleCopy = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.Key);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 2000);
      showToast("Key copied to clipboard", "success");
    } catch {
      // Clipboard can be blocked outside a secure/user-activated context — the field stays selectable.
    }
  };

  const handleRevoke = async (id: number) => {
    setRevokingId(id);
    try {
      await apiKeysService.revokeApiKey(id);
      showToast("API key revoked", "success");
      await load();
    } catch (err) {
      showToast(errorToString(err), "error");
    } finally {
      setRevokingId(null);
    }
  };

  if (keys === null && !loadError) {
    return (
      <Container size="2" pt="6" pb="9">
        <Flex align="center" gap="2">
          <Spinner size="3" />
          <Text color="gray">Loading API keys…</Text>
        </Flex>
      </Container>
    );
  }

  return (
    <Container size="2" pt="6" pb="9">
      <Flex align="center" justify="between" mb="2">
        <Heading size="6">API Keys</Heading>
        <Button onClick={openCreate}>
          <PlusIcon /> Create key
        </Button>
      </Flex>
      <Text as="p" size="2" color="gray" mb="5">
        Personal keys for programmatic access to the Learner Data Export API. Treat them like passwords — anyone with
        a key can export on your behalf.
      </Text>

      {loadError && (
        <Callout.Root color="red" mb="4">
          <Callout.Icon>
            <InfoCircledIcon />
          </Callout.Icon>
          <Callout.Text>{loadError}</Callout.Text>
        </Callout.Root>
      )}

      {keys && keys.length === 0 && (
        <Card>
          <Flex direction="column" align="center" gap="3" py="6">
            <Text color="gray">No API keys yet.</Text>
            <Button onClick={openCreate}>
              <PlusIcon /> Create your first key
            </Button>
          </Flex>
        </Card>
      )}

      <Flex direction="column" gap="3">
        {keys &&
          keys.map((key) => {
            const revoked = key.RevokedDate !== null;
            return (
              <Card key={key.Id}>
                <Flex align="center" justify="between" gap="3">
                  <Box>
                    <Flex align="center" gap="2" mb="1">
                      <Text weight="bold">{key.Label}</Text>
                      {revoked && <Badge color="gray">Revoked</Badge>}
                    </Flex>
                    <Text size="1" color="gray">
                      <code>{key.KeyPrefix}…</code> · created {formatDate(key.CreationDate)} ·{" "}
                      {key.LastUsedDate ? `last used ${formatDate(key.LastUsedDate)}` : "never used"}
                    </Text>
                  </Box>
                  {!revoked && (
                    <AlertDialog.Root>
                      <AlertDialog.Trigger>
                        <Button color="red" variant="soft" disabled={revokingId === key.Id}>
                          <TrashIcon /> {revokingId === key.Id ? "Revoking…" : "Revoke"}
                        </Button>
                      </AlertDialog.Trigger>
                      <AlertDialog.Content maxWidth="450px">
                        <AlertDialog.Title>Revoke “{key.Label}”?</AlertDialog.Title>
                        <AlertDialog.Description size="2">
                          Any application using this key will immediately lose access. This can&apos;t be undone.
                        </AlertDialog.Description>
                        <Flex gap="3" mt="4" justify="end">
                          <AlertDialog.Cancel>
                            <Button variant="soft" color="gray">
                              Cancel
                            </Button>
                          </AlertDialog.Cancel>
                          <AlertDialog.Action>
                            <Button color="red" onClick={() => handleRevoke(key.Id)}>
                              Revoke key
                            </Button>
                          </AlertDialog.Action>
                        </Flex>
                      </AlertDialog.Content>
                    </AlertDialog.Root>
                  )}
                </Flex>
              </Card>
            );
          })}
      </Flex>

      <Dialog.Root open={createOpen} onOpenChange={(open) => !open && closeCreate()}>
        <Dialog.Content style={{ maxWidth: 520 }}>
          <Dialog.Title>Create API key</Dialog.Title>
          {!created ? (
            <>
              <Dialog.Description size="2" mb="3">
                Give the key a name so you can recognize it later.
              </Dialog.Description>
              <TextField.Root
                placeholder="e.g. my-export-script"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                autoFocus
              />
              <Flex gap="3" mt="4" justify="end">
                <Dialog.Close>
                  <Button variant="soft" color="gray">
                    Cancel
                  </Button>
                </Dialog.Close>
                <Button onClick={handleCreate} disabled={creating || !label.trim()}>
                  {creating ? "Creating…" : "Create key"}
                </Button>
              </Flex>
            </>
          ) : (
            <>
              <Dialog.Description size="2" mb="3">
                Copy your key now — <strong>it won&apos;t be shown again.</strong>
              </Dialog.Description>
              <Flex gap="2" align="center">
                <Box style={{ flex: 1 }}>
                  <TextField.Root value={created.Key} readOnly />
                </Box>
                <IconButton variant="soft" onClick={handleCopy} aria-label="Copy key">
                  {copied ? <CheckIcon /> : <CopyIcon />}
                </IconButton>
              </Flex>
              <Callout.Root color="amber" mt="3">
                <Callout.Icon>
                  <InfoCircledIcon />
                </Callout.Icon>
                <Callout.Text>Store it somewhere safe. You can revoke it here at any time.</Callout.Text>
              </Callout.Root>
              <Flex mt="4" justify="end">
                <Dialog.Close>
                  <Button onClick={closeCreate}>Done</Button>
                </Dialog.Close>
              </Flex>
            </>
          )}
        </Dialog.Content>
      </Dialog.Root>
    </Container>
  );
}
