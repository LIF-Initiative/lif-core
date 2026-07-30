import { useEffect, useState } from "react";
import { Box, Button, Callout, Card, Container, Flex, Heading, IconButton, Select, Spinner, Text } from "@radix-ui/themes";
import { CheckIcon, CopyIcon, InfoCircledIcon, PlayIcon } from "@radix-ui/react-icons";
import exportService, { DataFormat } from "../services/exportService";
import personasService, { Persona } from "../services/personasService";
import JsonHighlight from "../components/JsonHighlight/JsonHighlight";
import { useToast } from "../context/ToastContext";

function errorMessage(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e?.response?.data?.detail || e?.message || fallback;
}

export default function ExportPlayground() {
  const { showToast } = useToast();

  const [personas, setPersonas] = useState<Persona[]>([]);
  const [formats, setFormats] = useState<DataFormat[]>([]);
  const [loadingMeta, setLoadingMeta] = useState(true);
  const [metaError, setMetaError] = useState<string | null>(null);

  const [learnerId, setLearnerId] = useState("");
  const [formatIdx, setFormatIdx] = useState("");

  const [output, setOutput] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoadingMeta(true);
      const [personaResult, formatResult] = await Promise.allSettled([
        personasService.getPersonas(),
        exportService.getAvailableDataFormats(),
      ]);
      if (!active) return;
      const errors: string[] = [];
      if (personaResult.status === "fulfilled") setPersonas(personaResult.value);
      else errors.push("test learners");
      if (formatResult.status === "fulfilled") setFormats(formatResult.value.DataFormats ?? []);
      else errors.push("data formats");
      setMetaError(errors.length ? `Could not load ${errors.join(" or ")}. Check that you're signed in and the services are reachable.` : null);
      setLoadingMeta(false);
    })();
    return () => {
      active = false;
    };
  }, []);

  const selectedFormat = formatIdx === "" ? undefined : formats[Number(formatIdx)];
  const canSubmit = Boolean(learnerId) && Boolean(selectedFormat) && !submitting;

  const handleSubmit = async () => {
    if (!learnerId || !selectedFormat) return;
    setSubmitting(true);
    setExportError(null);
    setOutput(null);
    try {
      const data = await exportService.runExport({
        learnerId,
        dataModelName: selectedFormat.name,
        dataModelVersion: selectedFormat.version,
        dataModelContributorOrganization: selectedFormat.contributorOrganization,
      });
      setOutput(data);
    } catch (err) {
      setExportError(errorMessage(err, "Export failed."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(output, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      showToast("Copy failed — the output is still selectable", "error");
    }
  };

  return (
    <Container size="3" py="5">
      <Heading size="6" mb="1">
        Export Playground
      </Heading>
      <Text as="p" color="gray" mb="4">
        Try the Learner Data Export API: pick a test learner and an output format, then run the export.
      </Text>

      <Card mb="4">
        <Flex direction="column" gap="3" p="2">
          <Box>
            <Text as="label" size="2" weight="bold" mb="1" style={{ display: "block" }}>
              Test learner
            </Text>
            <Select.Root value={learnerId} onValueChange={setLearnerId} disabled={loadingMeta || personas.length === 0}>
              <Select.Trigger placeholder="Select a test learner" />
              <Select.Content>
                {personas.map((p) => (
                  <Select.Item key={p.identifier} value={p.identifier}>
                    {p.firstname} {p.lastname} ({p.identifier})
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </Box>

          <Box>
            <Text as="label" size="2" weight="bold" mb="1" style={{ display: "block" }}>
              Output format
            </Text>
            <Select.Root value={formatIdx} onValueChange={setFormatIdx} disabled={loadingMeta || formats.length === 0}>
              <Select.Trigger placeholder="Select an output format" />
              <Select.Content>
                {formats.map((f, i) => (
                  <Select.Item key={`${f.name}-${f.version}-${f.contributorOrganization}`} value={String(i)}>
                    {f.name} v{f.version} — {f.contributorOrganization}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </Box>

          <Flex align="center" gap="3">
            <Button onClick={handleSubmit} disabled={!canSubmit}>
              {submitting ? <Spinner /> : <PlayIcon />} Run export
            </Button>
            {loadingMeta && (
              <Text size="2" color="gray">
                <Spinner /> Loading learners and formats…
              </Text>
            )}
          </Flex>
        </Flex>
      </Card>

      {metaError && (
        <Callout.Root color="amber" mb="4">
          <Callout.Icon>
            <InfoCircledIcon />
          </Callout.Icon>
          <Callout.Text>{metaError}</Callout.Text>
        </Callout.Root>
      )}

      {exportError && (
        <Callout.Root color="red" mb="4">
          <Callout.Icon>
            <InfoCircledIcon />
          </Callout.Icon>
          <Callout.Text>{exportError}</Callout.Text>
        </Callout.Root>
      )}

      {output !== null && !submitting && (
        <Card>
          <Flex justify="between" align="center" mb="2">
            <Text size="2" weight="bold">
              Result
            </Text>
            <IconButton variant="soft" onClick={handleCopy} aria-label="Copy result">
              {copied ? <CheckIcon /> : <CopyIcon />}
            </IconButton>
          </Flex>
          <JsonHighlight value={output} />
        </Card>
      )}
    </Container>
  );
}
