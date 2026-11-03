/**
 * Whether a model is an overlay: built on a base model, reading its elements through inclusion rows.
 * Decided by BaseDataModelId, not Type, because a converted overlay keeps its Type (#1388). The
 * backend's model_converter.is_overlay also checks for inclusion rows, which conversion clears in the
 * same transaction as BaseDataModelId.
 */
export const isOverlayModel = (model?: { BaseDataModelId?: number | null } | null): boolean =>
    model?.BaseDataModelId != null;
