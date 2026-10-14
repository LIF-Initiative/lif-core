import React from "react";
import * as RdxAlertDialog from "@radix-ui/react-alert-dialog";

export interface DetachSourcesDialogProps {
  open: boolean;
  count: number; // number of source attributes to remove
  willDeleteTransformation: boolean; // true if removing last sources => deleting transformation
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onOpenChange?: (open: boolean) => void;
}

const DetachSourcesDialog: React.FC<DetachSourcesDialogProps> = ({
  open,
  count,
  willDeleteTransformation,
  busy = false,
  onCancel,
  onConfirm,
  onOpenChange,
}) => {
  const title = willDeleteTransformation
    ? 'Delete Transformation'
    : (count === 1 ? 'Remove Source Attribute' : 'Remove Source Attributes');
  const actionLabel = willDeleteTransformation
    ? (busy ? 'Deleting...' : 'Delete')
    : (busy ? 'Removing...' : 'Remove');
  return (
    <RdxAlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <RdxAlertDialog.Portal>
        <RdxAlertDialog.Overlay className="mappings-alert-overlay" />
        <RdxAlertDialog.Content className="mappings-alert-content">
          <RdxAlertDialog.Title className="mappings-alert-title">
            {title}
          </RdxAlertDialog.Title>
          <RdxAlertDialog.Description className="mappings-alert-desc">
            {willDeleteTransformation ? (
              <>
                You are about to remove {count} source attribute{count>1?'s':''}. This is the last source set for this transformation, so the entire transformation (including its expression) will be <strong>deleted permanently</strong>. This action cannot be undone.
              </>
            ) : (
              <>Are you sure you want to remove {count} source attribute{count>1?'s':''} from this transformation? The transformation and its expression will remain; only the selected source mapping{count>1?'s':''} will be removed.</>
            )}
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
                className={`mappings-alert-btn ${willDeleteTransformation ? 'mappings-alert-btn--danger' : 'mappings-alert-btn--warn'}`}
                disabled={busy}
                onClick={onConfirm}
              >
                {actionLabel}
              </button>
            </RdxAlertDialog.Action>
          </div>
        </RdxAlertDialog.Content>
      </RdxAlertDialog.Portal>
    </RdxAlertDialog.Root>
  );
};

export default DetachSourcesDialog;
