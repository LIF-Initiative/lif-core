import React from "react";
import { Dialog } from "@radix-ui/themes";
import GroupDetailsEditor from "@/components/GroupDetailsEditor/GroupDetailsEditor";
import type { CreateTransformationGroup } from "@/services/transformationsService";
import type { TransformationGroupDetails } from "@/services/transformationsService";

export interface EditGroupDialogProps {
  open: boolean;
  group: TransformationGroupDetails | null;
  onOpenChange?: (open: boolean) => void;
  onSave: (updates: Partial<CreateTransformationGroup>) => Promise<void> | void;
  onCancel: () => void;
}

const EditGroupDialog: React.FC<EditGroupDialogProps> = ({ open, group, onOpenChange, onSave, onCancel }) => {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="800px" style={{ maxHeight: '85vh', overflow: 'auto' }}>
        <Dialog.Title>Edit Mapping Group Details</Dialog.Title>
        {group && (
          <GroupDetailsEditor group={group} onCancel={onCancel} onSave={onSave} />
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
};

export default EditGroupDialog;
