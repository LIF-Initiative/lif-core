import React from "react";
import { Dialog } from "@radix-ui/themes";
import ExpressionEditor from "@/components/ExpressionEditor/ExpressionEditor";
import type { DataModelWithDetailsWithTree } from "@/types";
import type { TransformationData } from "@/services/transformationsService";

export interface ExpressionEditorDialogProps {
  open: boolean;
  transformation: TransformationData | null;
  onOpenChange?: (open: boolean) => void;
  onSave: (update: { expression: string; expressionLanguage: string; name?: string }) => void;
  onCancel: () => void;
  sourceModel?: DataModelWithDetailsWithTree | null;
  targetPath?: string | null;
  targetJsonSchema?: any;
}

const ExpressionEditorDialog: React.FC<ExpressionEditorDialogProps> = ({ open, transformation, onOpenChange, onSave, onCancel, sourceModel, targetPath, targetJsonSchema }) => {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="900px" style={{ maxHeight: '85vh', overflow: 'auto' }}>
        <Dialog.Title>Edit Transformation Expression</Dialog.Title>
        {transformation && (
          <ExpressionEditor
            transformation={transformation}
            onSave={onSave}
            onCancel={onCancel}
            preloadedSourceModel={sourceModel || undefined}
            targetJsonataPath={targetPath || undefined}
            targetJsonSchema={targetJsonSchema}
          />
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
};

export default ExpressionEditorDialog;
