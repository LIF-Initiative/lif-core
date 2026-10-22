import { IconButton, ThickCheckIcon } from "@radix-ui/themes";
import { TrashIcon } from "@radix-ui/react-icons";
import React, { useCallback, useEffect, useState } from "react";
import DOMPurify from "dompurify";

import "./EditableFormula.css";

interface EditableFormulaProps {
    formula: string;
    onFormulaChange: (formula: string) => void;
}

const EditableFormula: React.FC<EditableFormulaProps> = ({ formula, onFormulaChange }) => {
    const [editing, setEditing] = useState(false);
    const [localFormula, setLocalFormula] = useState(formula);
    const [displayFormula, setDisplayFormula] = useState(formula);

    const handleSave = useCallback(() => {
        onFormulaChange(localFormula);
        const html = convertFormulaToHTMLForDisplay(localFormula);
        setDisplayFormula(html);
        setEditing(false);
    }, [localFormula, onFormulaChange]);

    const handleCancel = useCallback(() => {
        setLocalFormula(formula);
        setDisplayFormula(convertFormulaToHTMLForDisplay(formula));
        setEditing(false);
    }, [formula]);

    const handleInput = useCallback((e: React.FormEvent<HTMLDivElement>) => {
        setEditing(true);
        const target = e.target as HTMLDivElement;
        // need to get every child div as a line with a newline character
        const localFormula = Array.from(target.childNodes)
            .map((child) => child.textContent)
            .join('\n');
        setLocalFormula(localFormula);
    }, []);

    const convertFormulaToHTMLForDisplay = (formula: string) => {
        if(!formula) { return ''; }
        const html = formula.split('\n').map((line, index) => (
            `<div>${line}</div>`
        )).join('');
        return DOMPurify.sanitize(html);
    };

    useEffect(() => {
        setDisplayFormula(convertFormulaToHTMLForDisplay(formula));
    }, [formula]);

    return (
        <div className="editable-formula">
            <div
                contentEditable
                spellCheck={false}
                suppressContentEditableWarning
                onInput={handleInput}
                className="formula-input"
                dangerouslySetInnerHTML={{ __html: displayFormula }}
            ></div>
            {editing ? (
                <div className="editing-controls">
                    <IconButton className="editing-button" size="1" onClick={handleSave}>
                        <ThickCheckIcon />
                    </IconButton>
                    <IconButton className="editing-button" size="1" onClick={handleCancel}>
                        <TrashIcon />
                    </IconButton>
                </div>
            ) : null}
        </div>
    );
};

export default EditableFormula;
