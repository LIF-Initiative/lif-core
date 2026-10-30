import React, { useMemo, useState } from "react";
import { Button, Dialog, Flex, Select, Text } from "@radix-ui/themes";
import RefusalList from "@/components/RefusalList/RefusalList";
import { describePortableFailure, exportPortableCrosswalk, type PortableFailure } from "@/services/portableService";
import { downloadBlobFile } from "@/utils/downloadJsonFile";

/** A model as this dialog needs it: its name and its value sets. */
export interface CrosswalkModel {
  name: string;
  valueSets: Array<{ Id: number; Name: string }>;
}

export interface CrosswalkDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  source: CrosswalkModel | null;
  target: CrosswalkModel | null;
  /** Open the import dialog; a crosswalk file names its own value sets, so nothing is picked here. */
  onImport: () => void;
  onExported: (message: string) => void;
}

interface ValueSetSelectProps {
  label: string;
  model: CrosswalkModel | null;
  value: number | null;
  onChange: (id: number) => void;
}

const ValueSetSelect: React.FC<ValueSetSelectProps> = ({ label, model, value, onChange }) => {
  const valueSets = useMemo(
    () => (model?.valueSets ?? []).slice().sort((a, b) => a.Name.localeCompare(b.Name)),
    [model]
  );
  return (
    <Flex direction="column" gap="1" style={{ flex: 1, minWidth: 0 }}>
      <Text size="2" weight="bold">{label}: {model?.name ?? "no model selected"}</Text>
      {valueSets.length ? (
        <Select.Root value={value != null ? String(value) : undefined} onValueChange={(next) => onChange(Number(next))}>
          <Select.Trigger placeholder="Choose a value set…" />
          <Select.Content>
            {valueSets.map((valueSet) => (
              <Select.Item key={valueSet.Id} value={String(valueSet.Id)}>{valueSet.Name}</Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      ) : (
        <Text size="2" color="gray">This model has no value sets.</Text>
      )}
    </Flex>
  );
};

/**
 * Export the value mappings from a value set in the source model to one in the target model as a portable
 * crosswalk file, or hand off to importing one.
 */
const CrosswalkDialog: React.FC<CrosswalkDialogProps> = ({ open, onOpenChange, source, target, onImport, onExported }) => {
  const [sourceValueSetId, setSourceValueSetId] = useState<number | null>(null);
  const [targetValueSetId, setTargetValueSetId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [failure, setFailure] = useState<PortableFailure | null>(null);

  const close = () => {
    setSourceValueSetId(null);
    setTargetValueSetId(null);
    setFailure(null);
    onOpenChange(false);
  };

  const handleExport = async () => {
    if (sourceValueSetId == null || targetValueSetId == null) return;
    const sourceName = source?.valueSets.find((v) => v.Id === sourceValueSetId)?.Name ?? "source";
    const targetName = target?.valueSets.find((v) => v.Id === targetValueSetId)?.Name ?? "target";
    setExporting(true);
    setFailure(null);
    try {
      const file = await exportPortableCrosswalk(sourceValueSetId, targetValueSetId);
      // A pair with no live value mappings still exports, with no entries, so say how many there are.
      const entries = (JSON.parse(await file.text()).Entries ?? []).length;
      const filename = downloadBlobFile(
        file, `${source?.name}_${sourceName}_to_${target?.name}_${targetName}`, ".lif-mdr-crosswalk.json"
      );
      onExported(`${filename} downloaded with ${entries} entr${entries === 1 ? "y" : "ies"}`);
      close();
    } catch (error) {
      setFailure(describePortableFailure(error));
    } finally {
      setExporting(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!next) close(); }}>
      <Dialog.Content maxWidth="720px" style={{ maxHeight: "85vh", overflow: "auto" }}>
        <Dialog.Title>Crosswalks</Dialog.Title>
        <Dialog.Description size="2" mb="3">
          A crosswalk maps the values of one value set to the values of another. Export one between the source and
          target models shown here, or import a crosswalk file into this install.
        </Dialog.Description>

        <Flex gap="4" mb="3">
          <ValueSetSelect label="Source" model={source} value={sourceValueSetId} onChange={setSourceValueSetId} />
          <ValueSetSelect label="Target" model={target} value={targetValueSetId} onChange={setTargetValueSetId} />
        </Flex>

        {failure && <RefusalList failure={failure} action="export" />}

        <Flex gap="3" mt="4" justify="between">
          <Button variant="soft" onClick={() => { close(); onImport(); }} disabled={exporting}>
            Import a crosswalk file…
          </Button>
          <Flex gap="3">
            <Button variant="soft" onClick={close} disabled={exporting}>Cancel</Button>
            <Button onClick={handleExport} disabled={exporting || sourceValueSetId == null || targetValueSetId == null}>
              {exporting ? "Exporting…" : "Export"}
            </Button>
          </Flex>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
};

export default CrosswalkDialog;
