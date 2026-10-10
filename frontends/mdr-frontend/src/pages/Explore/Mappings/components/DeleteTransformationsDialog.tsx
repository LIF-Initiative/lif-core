import React from "react";
import * as RdxAlertDialog from "@radix-ui/react-alert-dialog";

export interface DeleteTransformationsDialogProps {
  open: boolean;
  count: number;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onOpenChange?: (open: boolean) => void;
}

const DeleteTransformationsDialog: React.FC<DeleteTransformationsDialogProps> = ({
  open,
  count,
  busy = false,
  onCancel,
  onConfirm,
  onOpenChange,
}) => {
  return (
    <RdxAlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <RdxAlertDialog.Portal>
        <RdxAlertDialog.Overlay className="mappings-alert-overlay" />
        <RdxAlertDialog.Content className="mappings-alert-content">
          <RdxAlertDialog.Title className="mappings-alert-title">
            Delete Transformation{count > 1 ? 's' : ''}
          </RdxAlertDialog.Title>
          <RdxAlertDialog.Description className="mappings-alert-desc">
            Are you sure you want to delete {count} transformation{count > 1 ? 's' : ''}? This action cannot be undone.
          </RdxAlertDialog.Description>
          <div className="mappings-alert-actions">
            <RdxAlertDialog.Cancel asChild>
              <button
                type="button"
                className="mappings-alert-btn"
                disabled={busy}
                onClick={onCancel}
              >
                Cancel
              </button>
            </RdxAlertDialog.Cancel>
            <RdxAlertDialog.Action asChild>
              <button
                type="button"
                className="mappings-alert-btn mappings-alert-btn--danger"
                disabled={busy}
                onClick={onConfirm}
              >
                {busy ? 'Deleting...' : 'Delete'}
              </button>
            </RdxAlertDialog.Action>
          </div>
        </RdxAlertDialog.Content>
      </RdxAlertDialog.Portal>
    </RdxAlertDialog.Root>
  );
};

export default DeleteTransformationsDialog;
