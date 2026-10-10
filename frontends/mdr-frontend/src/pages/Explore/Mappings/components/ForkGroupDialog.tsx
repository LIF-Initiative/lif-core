import React from "react";
import { Dialog } from "@radix-ui/themes";

export interface ForkGroupDialogProps {
  open: boolean;
  forkBump: 'major' | 'minor';
  preview?: string;
  currentVersion?: string;
  onOpenChange?: (open: boolean) => void;
  onChangeBump: (bump: 'major' | 'minor') => void;
  onCancel: () => void;
  onFork: () => void | Promise<void>;
}

const ForkGroupDialog: React.FC<ForkGroupDialogProps> = ({
  open,
  forkBump,
  preview,
  currentVersion,
  onOpenChange,
  onChangeBump,
  onCancel,
  onFork,
}) => {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="520px">
        <Dialog.Title>Fork to New Version</Dialog.Title>
        <p className="mappings-dialog-text">
          This will create a new mapping group with a bumped version and cloned transformations.
        </p>
        <div className="mappings-fork-options">
          <div className="mappings-fork-toggle">
            <label>
              <input
                type="radio"
                name="fork-bump"
                value="major"
                checked={forkBump === 'major'}
                onChange={() => onChangeBump('major')}
              />{' '}
              Major
            </label>
            <label>
              <input
                type="radio"
                name="fork-bump"
                value="minor"
                checked={forkBump === 'minor'}
                onChange={() => onChangeBump('minor')}
              />{' '}
              Minor
            </label>
          </div>
          <div className="mappings-fork-preview">
            Next version: <strong>v{preview || currentVersion || '?'}</strong>
          </div>
        </div>
        <div className="mappings-dialog-actions">
          <button className="mappings-alert-btn" type="button" onClick={onCancel}>Cancel</button>
          <button className="mappings-alert-btn mappings-alert-btn--danger" type="button" onClick={() => onFork()}>Fork Group</button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
};

export default ForkGroupDialog;
