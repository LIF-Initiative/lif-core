import React, { useMemo, useState } from "react";
import {
    CreateTransformationGroup,
    TransformationGroupDetails,
} from "@/services/transformationsService";
import "./GroupDetailsEditor.css";

export interface GroupDetailsEditorProps {
    group: TransformationGroupDetails;
    onSave: (
        updates: Partial<CreateTransformationGroup>
    ) => void | Promise<void>;
    onCancel: () => void;
}

// Note: This component is just the body for a Dialog; parent provides the Dialog chrome.
const GroupDetailsEditor: React.FC<GroupDetailsEditorProps> = ({
    group,
    onSave,
    onCancel,
}) => {
    const [name, setName] = useState(group.Name ?? '');
    const [description, setDescription] = useState(group.Description ?? '');
    const [notes, setNotes] = useState(group.Notes ?? '');
    const [activationDate, setActivationDate] = useState(
        group.ActivationDate ? group.ActivationDate.substring(0, 10) : ''
    );
    const [deprecationDate, setDeprecationDate] = useState(
        group.DeprecationDate ? group.DeprecationDate.substring(0, 10) : ''
    );
    const [saving, setSaving] = useState(false);

    const readonly = useMemo(
        () => ({
            source:
                group.SourceDataModelName || String(group.SourceDataModelId),
            target:
                group.TargetDataModelName || String(group.TargetDataModelId),
            version: group.GroupVersion,
            contributor: group.Contributor || '',
            org: group.ContributorOrganization || '',
            created: group.CreationDate
                ? group.CreationDate.substring(0, 10)
                : '',
        }),
        [group]
    );

    const handleSave = async () => {
        setSaving(true);
        try {
            const updates: Partial<CreateTransformationGroup> = {
                Name: name,
                Description: description,
                Notes: notes,
                ActivationDate: activationDate || undefined,
                DeprecationDate: deprecationDate || undefined,
            };
            await onSave(updates);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="group-editor">
            <div
                className="group-editor__summary"
                aria-label="Group details summary"
            >
                <div className="group-editor__summary-row">
                    <span className="group-editor__pill">
                        <strong>Source:</strong> {readonly.source}
                    </span>
                    <span className="group-editor__arrow" aria-hidden>
                        →
                    </span>
                    <span className="group-editor__pill">
                        <strong>Target:</strong> {readonly.target}
                    </span>
                    <span className="group-editor__badge">
                        v{readonly.version}
                    </span>
                </div>
                <div className="group-editor__summary-meta">
                    {readonly.created && (
                        <span>
                            <strong>Created:</strong> {readonly.created}
                        </span>
                    )}
                    {readonly.contributor && (
                        <span>
                            <strong>Contributor:</strong> {readonly.contributor}
                        </span>
                    )}
                    {readonly.org && (
                        <span>
                            <strong>Organization:</strong> {readonly.org}
                        </span>
                    )}
                </div>
            </div>

            <div className="group-editor__grid">
                <label className="group-editor__label" htmlFor="ged-name">
                    Name
                </label>
                <input
                    id="ged-name"
                    className="group-editor__input"
                    placeholder="Group name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                />

                <label className="group-editor__label" htmlFor="ged-activation">
                    Activation Date
                </label>
                <input
                    id="ged-activation"
                    className="group-editor__input"
                    type="date"
                    value={activationDate}
                    onChange={(e) => setActivationDate(e.target.value)}
                />

                <label
                    className="group-editor__label"
                    htmlFor="ged-deprecation"
                >
                    Deprecation Date
                </label>
                <input
                    id="ged-deprecation"
                    className="group-editor__input"
                    type="date"
                    value={deprecationDate}
                    onChange={(e) => setDeprecationDate(e.target.value)}
                />

                <label
                    className="group-editor__label group-editor__label--block"
                    htmlFor="ged-description"
                >
                    Description
                </label>
                <textarea
                    id="ged-description"
                    className="group-editor__textarea group-editor__textarea--block"
                    rows={3}
                    placeholder="Short description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                />

                <label
                    className="group-editor__label group-editor__label--block"
                    htmlFor="ged-notes"
                >
                    Notes
                </label>
                <textarea
                    id="ged-notes"
                    className="group-editor__textarea group-editor__textarea--block"
                    rows={3}
                    placeholder="Additional notes"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                />
            </div>

            <div className="group-editor__actions">
                <button
                    type="button"
                    className="group-editor__btn"
                    onClick={onCancel}
                    disabled={saving}
                >
                    Cancel
                </button>
                <button
                    type="button"
                    className="group-editor__btn group-editor__btn--primary"
                    onClick={handleSave}
                    disabled={saving}
                >
                    {saving ? 'Saving…' : 'Save Changes'}
                </button>
            </div>
        </div>
    );
};

export default GroupDetailsEditor;
