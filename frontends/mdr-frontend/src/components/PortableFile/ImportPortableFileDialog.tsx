import React, { useState } from "react";
import { Button, Dialog, Flex } from "@radix-ui/themes";
import FileInput from "@/components/FileInput/FileInput";
import RefusalList from "@/components/RefusalList/RefusalList";
import { describePortableFailure, type PortableFailure } from "@/services/portableService";

export interface ImportPortableFileDialogProps<T> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  importFile: (file: File) => Promise<T>;
  /** Called after a successful import; the dialog then closes. */
  onImported: (result: T, file: File) => Promise<void> | void;
}

/**
 * Pick a portable file and import it. The file is sent as it is: the API checks it, and on a refusal
 * the dialog stays open with every reason, so the file can be fixed and tried again.
 */
function ImportPortableFileDialog<T>({
  open,
  onOpenChange,
  title,
  description,
  importFile,
  onImported,
}: ImportPortableFileDialogProps<T>) {
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [failure, setFailure] = useState<PortableFailure | null>(null);

  const close = () => {
    setFile(null);
    setFailure(null);
    onOpenChange(false);
  };

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);
    setFailure(null);
    try {
      const result = await importFile(file);
      await onImported(result, file);
      close();
    } catch (error) {
      setFailure(describePortableFailure(error));
    } finally {
      setImporting(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!next) close(); }}>
      <Dialog.Content maxWidth="800px" style={{ maxHeight: "85vh", overflow: "auto" }}>
        <Dialog.Title>{title}</Dialog.Title>
        <Dialog.Description size="2" mb="3">{description}</Dialog.Description>
        <FileInput
          id="portableFileInput"
          label="Select a portable file to import:"
          placeholder="Choose a file…"
          accept=".json,application/json"
          disabled={importing}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
            setFailure(null);
            setFile(e.target.files && e.target.files.length > 0 ? e.target.files[0] : null);
          }}
        />
        {failure && <div style={{ marginTop: "1rem" }}><RefusalList failure={failure} action="import" /></div>}
        <Flex gap="3" mt="4" justify="end">
          <Button variant="soft" onClick={close} disabled={importing}>Cancel</Button>
          <Button onClick={handleImport} disabled={importing || !file}>{importing ? "Importing…" : "Import"}</Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}

export default ImportPortableFileDialog;
