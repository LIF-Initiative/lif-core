import React, { useState } from 'react';
import { Checkbox, Dialog, Text, Button } from '@radix-ui/themes';
import type { TransformationGroupDetails } from '../../../../services/transformationsService';
import { importTransformationsForGroup } from '../../../../services/transformationsService';
import { isValidJSONFile } from '../../../../utils/objectUtils';
import { errorToString } from '../../../../utils/errorUtils';
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
  const [file, setFile] = useState<File | null>(null);
  const [reportMissing, setMissingPath] = useState(true);
  const [saving, setSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [newId, setNewId] = useState<number | null>(null);

  if (!group) return null;

  const closeDialog = (useOnSaved: boolean = false) => {
    setFile(null);
    setCreateError(null);
    setSuccessMessage(null);
    setNewId(null);
    if (useOnSaved && onSaved) onSaved();
    else onCancel();
  };

  const parseFile = async (file: File) => {
    setFile(null);
    try {
      if(isValidJSONFile(file)) {
        setFile(file);
      }
    } catch (err) {
      setCreateError(errorToString(err));
    }  
  };
  
  const handleSave = async () => {
    setSaving(true);
    setNewId(null);
    try {
      try {
        // Caution: param @allowMissingPaths is the inverse of the displayed reportMissing value
        const data = await importTransformationsForGroup(group.Id, file, !reportMissing, null);
        setCreateError(null);
        if (data.Success) {
          const count = data.SkippedTransformationCount;
          let msg = `Successfully imported ${file?.name} with ${data.ImportedTransformationCount} transformations for ${group.Name}.`
          if (count) {
            msg += `\n\n${count} transformation(s) were skipped. See the console for the full list of skipped transformations and reasons.`;
            console.log('Skipped transformation imports:', data.SkippedTransformations);
          }
          setSuccessMessage(msg);
          setNewId(data.TransformationGroupId);
        } else {
          const count = data.SkippedTransformationCount || -1;
          const msg = `Import failed as ${count} transformation(s) were skipped. See the console for the full list of skipped transformations and reasons.`;
          console.log('Skipped transformation imports:', data.SkippedTransformations);
          setCreateError(msg);
        }
      } catch (e) {
        setSuccessMessage(null);
        setCreateError(errorToString(e));
      }
    } finally {
      setSaving(false);
    }
  };

  const handlePostSave = () => {
    window.location.href = `/explore/data-mappings/${newId}`;
    closeDialog();
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="800px" style={{ maxHeight: '85vh', overflow: 'auto' }}>
        <Dialog.Title>Update/Branch Group Transformations</Dialog.Title>

        <Dialog.Description size="2" mb="4">
          {!newId && !createError && !successMessage && (
            <p>
              Import a JSON file, in the format exported by the Export button, to update or branch the transformation group.
              The version will update and a new ID will be assigned. Once imported, you can view the new transformations in the mapping explorer.
            </p>
          )}
          {successMessage && ( <Text color="green" size="2" mb="3" style={{ whiteSpace: "pre-line" }}>{successMessage}</Text> )}
          {createError && ( <Text color="red" size="2" mb="3" style={{ whiteSpace: "pre-line" }}>{createError}</Text> )}
        </Dialog.Description>

        <div className={`bulk-xforms-dialog__body ${newId ? 'hide' : ''}`}>
          <div className="file-input__fields">
            <FileInput
              id="fileInput"
              label="Select a file to import:"
              description="Import a mapping group from a JSON file. The file should be in the format exported by the 'Export Group' action."
              placeholder="Choose a file…"
              accept=".json,application/json"
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                if (e.target.files && e.target.files.length > 0) {
                  parseFile(e.target.files[0]);
                }
              }}
            />
            <div>
              <label htmlFor="cbxMPath">Report missing paths?</label>{" "}
              <Checkbox id="cbxMPath" className="import-group-dialog__checkbox" checked={reportMissing} onClick={() => setMissingPath(!reportMissing)} />
            </div>
          </div>
        </div>

        <div className={`bulk-xforms-dialog__actions`}>
        {!newId ? (
          <>
          <Button onClick={() => closeDialog()} className="rt-variant-soft" disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving || !file}>{saving ? 'Saving…' : 'Save'}</Button>
          </>
        ) : (
          <>
          <Button className="rt-variant-soft" onClick={() => closeDialog(true)}>Stay</Button>
          <Button onClick={handlePostSave}>See New Import</Button>
          </>
        )}
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
};

export default ImportGroupDialog;
