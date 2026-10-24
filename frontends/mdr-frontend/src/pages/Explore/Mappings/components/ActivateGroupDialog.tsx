import React from "react";
import { Dialog } from "@radix-ui/themes";

export interface ActivateGroupDialogProps {
  open: boolean;
  version?: string;
  // Whether another version of the pair is live now, and its version when known.
  hasLiveVersion: boolean;
  activeVersion?: string;
  onOpenChange?: (open: boolean) => void;
  onCancel: () => void;
  onActivate: () => void | Promise<void>;
}

const ActivateGroupDialog: React.FC<ActivateGroupDialogProps> = ({
  open,
  version,
  hasLiveVersion,
  activeVersion,
  onOpenChange,
  onCancel,
  onActivate,
}) => {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="520px">
        <Dialog.Title>Activate v{version || '?'}</Dialog.Title>
        <p className="mappings-dialog-text">
          This makes v{version || '?'} the live version for this source and target, starting now. The Translator uses
          the live version.
        </p>
        {hasLiveVersion ? (
          <p className="mappings-dialog-text">
            {activeVersion ? `v${activeVersion}, the current live version,` : 'The current live version'} will be
            deprecated now. To roll back, activate it again.
          </p>
        ) : (
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
