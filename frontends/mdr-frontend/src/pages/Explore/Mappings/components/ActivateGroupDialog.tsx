import React from "react";
import { Dialog } from "@radix-ui/themes";

export interface ActivateGroupDialogProps {
  open: boolean;
  version?: string;
  // What is live now: another version (its version in activeVersion when known), nothing, or a tie
  // between versions that compare equal (the API's 409).
  currentLive: 'other' | 'none' | 'tie';
  activeVersion?: string;
  onOpenChange?: (open: boolean) => void;
  onCancel: () => void;
  onActivate: () => void | Promise<void>;
}

const ActivateGroupDialog: React.FC<ActivateGroupDialogProps> = ({
  open,
  version,
  currentLive,
  activeVersion,
  onOpenChange,
  onCancel,
  onActivate,
}) => {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="520px">
        <Dialog.Title>Activate v{version || '?'}</Dialog.Title>
        <Dialog.Description className="mappings-dialog-text">
          This makes v{version || '?'} the live version for this source and target, starting now. The Translator
          uses the live version.
        </Dialog.Description>
        {currentLive === 'other' && (
          <p className="mappings-dialog-text">
            {activeVersion ? `v${activeVersion}, the current live version,` : 'The current live version'} will be
            deprecated now. To roll back, activate it again.
          </p>
        )}
        {currentLive === 'tie' && (
          <p className="mappings-dialog-text">
            Two versions are live with the same version number, so the Translator can't pick one. Every other live
            version will be deprecated now.
          </p>
        )}
        {currentLive === 'none' && (
          <p className="mappings-dialog-text">This source and target has no live version yet.</p>
        )}
        <div className="mappings-dialog-actions">
          <button className="mappings-alert-btn" type="button" onClick={onCancel}>Cancel</button>
          <button className="mappings-alert-btn mappings-alert-btn--danger" type="button" onClick={() => onActivate()}>
            Activate
          </button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
};

export default ActivateGroupDialog;
