import React, { useState } from 'react';
import { Checkbox, Dialog } from '@radix-ui/themes';
import type { TransformationGroupDetails } from '../../../../services/transformationsService';
import FileInput from '../../../../components/FileInput.tsx';

export interface ImportGroupDialogProps {
  open: boolean;
  group: TransformationGroupDetails | null;
  onOpenChange?: (open: boolean) => void;
  onSaved: () => Promise<void> | void;
  onCancel: () => void;
}

const ImportGroupDialog: React.FC<ImportGroupDialogProps> = ({
  open,
  group,
  onOpenChange,
  onSaved,
  onCancel,
}) => {
  if (!group) return;
  const [file, setFile] = useState<File | null>(null);
  const [reportMissing, setMissingPath] = useState(false);
  const [saving, setSaving] = useState(false);
  
  const parseFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        // TODO: Validate file contents here before allowing save
        if (reportMissing) {
          // TODO: Can we pre-test this? If so, we can warn the user before they click save, and provide details in the error.
        }
        setFile(file);
      } catch (e) {
        console.warn('Error parsing file: ' + (e as Error).message);
      } finally {
        // TODO: If needed, cleanup or final actions
      }
    };
    // reader.readAsText(file);
  };
  
  const handleSave = async () => {
    setSaving(true);
    try {
      // TODO: Use endpoint from https://github.com/LIF-Initiative/lif-core/issues/772
      // TODO: Hits new transofmrationService func that creates new Major Version Fork and returns custom error based on allowMissingPaths param
      if (onSaved) {
          try {onSaved(); }
          catch { /* ignore callback errors */ }
      }
    } finally {
      setSaving(false);
      onCancel();
    }
  };
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="800px" style={{ maxHeight: '85vh', overflow: 'auto' }}>
        <Dialog.Title>Import Group Transformations</Dialog.Title>

        <div className="bulk-xforms-dialog__body">
          <div>
            <FileInput
              id="fileInput"
              label="Select a file to import"
              description="Import a mapping group from a JSON file. The file should be in the format exported by the 'Export Group' action."
              placeholder="Choose a file…"
              accept=".json,application/json"
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                if (e.target.files && e.target.files.length > 0) {
                  parseFile(e.target.files[0]);
                }
              }}
            />
          </div>
          <div>
            <label htmlFor="cbxMPath">Report missing paths?</label>{" "}
            <Checkbox id="cbxMPath" className="import-group-dialog__checkbox" onClick={() => setMissingPath(!reportMissing)} />
          </div>
        </div>

        <div className="bulk-xforms-dialog__actions">
          <button
            type="button"
            className="bulk-xforms-btn bulk-xforms-btn--secondary"
            disabled={saving}
            onClick={onCancel}
          >Cancel</button>
          <button
            type="button"
            className="bulk-xforms-btn bulk-xforms-btn--primary"
            disabled={saving}
            onClick={handleSave}
          >{saving ? 'Saving…' : 'Save'}</button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
};

export default ImportGroupDialog;
