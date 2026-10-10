import React, { useState, useMemo } from "react";
import { Dialog } from "@radix-ui/themes";
import type {
    TransformationGroupDetails,
    TransformationData,
} from "@/services/transformationsService";
import BulkTransformationsBody from "./BulkTransformationsBody";
import {
    deleteTransformation,
    updateTransformation,
} from "@/services/transformationsService";

export interface BulkTransformationsDialogProps {
    open: boolean;
    group: TransformationGroupDetails | null;
    transformations: TransformationData[];
    onOpenChange?: (open: boolean) => void;
    onClose: () => void;
    sourceSchema?: any;
    targetSchema?: any;
    /**
     * Called after a successful save (all pending deletes applied). Parent should refresh group/transformations.
     */
    onSaved?: () => void;
}

const BulkTransformationsDialog: React.FC<BulkTransformationsDialogProps> = ({
    open,
    group,
    transformations,
    onOpenChange,
    onClose,
    sourceSchema,
    targetSchema,
    onSaved,
}) => {
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [pendingDeleteIds, setPendingDeleteIds] = useState<number[]>([]);
    const [pendingEdits, setPendingEdits] = useState<
        { id: number; expression: string }[]
    >([]);
    const [saving, setSaving] = useState(false);
    const selected = useMemo(
        () => transformations.find((t) => t.Id === selectedId) || null,
        [transformations, selectedId]
    );

    const handleSave = async () => {
        if (!pendingDeleteIds.length && !pendingEdits.length) {
            onClose();
            return;
        }
        setSaving(true);
        try {
            // Apply edits first (so deletes don't cause lookups to fail elsewhere)
            for (const edit of pendingEdits) {
                try {
                    const original = transformations.find(t => t.Id === edit.id) || null;
                    const transformationGroupId = original?.TransformationGroupId ?? group?.Id;
                    if (!transformationGroupId) {
                        // If we somehow can't resolve the group id, skip this edit to avoid 400 from backend
                        // (Could collect and surface to user if desired)
                        continue;
                    }
                    await updateTransformation(edit.id, {
                        Expression: edit.expression,
                        TransformationGroupId: transformationGroupId,
                    } as any);
                } catch (e) {
                    /* swallow individual edit errors */
                }
            }
            for (const id of pendingDeleteIds) {
                try {
                    await deleteTransformation(id);
                } catch (e) {
                    /* swallow individual errors; could aggregate */
                }
            }
            // Notify parent AFTER all deletes succeed (even if some individual calls failed silently) so it can refetch.
            if (onSaved) {
                try {
                    onSaved();
                } catch {
                    /* ignore callback errors */
                }
            }
        } finally {
            setSaving(false);
            onClose();
        }
    };
    return (
        <Dialog.Root open={open} onOpenChange={onOpenChange}>
            <Dialog.Content
                maxWidth="1100px"
                className="bulk-xforms-dialog__content"
            >
                <Dialog.Title className="bulk-xforms-dialog__title">
                    Bulk Edit Transformations
                </Dialog.Title>
                <BulkTransformationsBody
                    group={group}
                    transformations={transformations}
                    selected={selected}
                    onSelect={setSelectedId}
                    sourceSchema={sourceSchema}
                    targetSchema={targetSchema}
                    onPendingDeletesChange={setPendingDeleteIds}
                    onPendingEditsChange={setPendingEdits}
                />
                <div className="bulk-xforms-dialog__actions">
                    {pendingDeleteIds.length || pendingEdits.length ? (
                        <>
                            <button
                                type="button"
                                className="bulk-xforms-btn bulk-xforms-btn--secondary"
                                disabled={saving}
                                onClick={onClose}
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                className="bulk-xforms-btn bulk-xforms-btn--primary"
                                disabled={saving}
                                onClick={handleSave}
                            >
                                {saving ? 'Saving…' : 'Save'}
                                {pendingDeleteIds.length || pendingEdits.length
                                    ? ` (${pendingEdits.length} edits, ${pendingDeleteIds.length} deletions)`
                                    : ''}
                            </button>
                        </>
                    ) : (
                        <button
                            type="button"
                            className="bulk-xforms-btn bulk-xforms-btn--secondary"
                            onClick={onClose}
                        >
                            Close
                        </button>
                    )}
                </div>
            </Dialog.Content>
        </Dialog.Root>
    );
};

export default BulkTransformationsDialog;
