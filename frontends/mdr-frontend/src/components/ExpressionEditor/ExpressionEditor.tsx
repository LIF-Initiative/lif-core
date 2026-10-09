import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { TransformationData } from "@/services/transformationsService";
import jsonata from "jsonata";
import {
    getModelDetailsWithTree,
    generateSampleRecords,
} from "@/services/modelService";
import type { DataModelWithDetailsWithTree } from "@/types";
import "./ExpressionEditor.css";

// NOTE: This is the core editor BODY (not a dialog). Wrap it in your modal of choice.
// Minimal starting implementation – extend with validation, syntax highlighting, etc.

export interface ExpressionEditorProps {
    transformation: TransformationData;
    // Provide source model id so we can build sample data
    sourceDataModelId?: number; // optional; if missing no sample/preview
    preloadedSourceModel?: DataModelWithDetailsWithTree; // if provided, use directly (no fetch)
    // JSONata target path (Entity.Entity.Attribute). If provided and expression empty, we prefill assignment scaffold.
    targetJsonataPath?: string;
    // Generated JSON Schema for the target model (optional)
    targetJsonSchema?: any;
    onSave: (update: {
        expression: string;
        expressionLanguage: string;
        name?: string;
    }) => void;
    onCancel: () => void;
}

const OPERATORS = [
    '+',
    '-',
    '*',
    '/',
    '&', // JSONata string concatenation
    '||',
    '&&',
    '!',
    '^',
    '==',
    '===',
    '<=>',
    '!=',
    '>',
    '<',
    '>=',
    '<=',
    '[]',
    '" "', // literal space string for easy concatenation
];


// Common JSONata functions/snippets for quick insertion
const COMMON_FUNCTIONS: { label: string; snippet: string; description: string }[] = [
    { label: '$uppercase(str)', snippet: '$uppercase()', description: 'Uppercase a string' },
    { label: '$lowercase(str)', snippet: '$lowercase()', description: 'Lowercase a string' },
    { label: '$length(value)', snippet: '$length()', description: 'Length of string/array' },
    { label: '$substring(str,start,len?)', snippet: '$substring()', description: 'Substring by start index (0) and optional length' },
    { label: '$contains(str,substr)', snippet: '$contains()', description: 'True if string contains substring' },
    { label: '$match(str, /regex/)', snippet: '$match()', description: 'Regex match array' },
    { label: '$exists(path)', snippet: '$exists()', description: 'True if input exists / not empty' },
    { label: '$not(value)', snippet: '$not()', description: 'Logical NOT' },
    { label: '$number(value)', snippet: '$number()', description: 'Cast to number' },
    { label: '$now()', snippet: '$now()', description: 'Current timestamp as ms since epoch' },
    { label: '$toMillis(datetime)', snippet: '$toMillis()', description: 'Date/time to ms epoch' },
    { label: '$formatNumber(num,picture)', snippet: '$formatNumber()', description: 'Format number by picture' },
    { label: '$sum(array)', snippet: '$sum()', description: 'Sum numeric array' },
    { label: '$map(array, function($v){$v})', snippet: '$map()' , description: 'Apply function to each element' },
];

const ExpressionEditor: React.FC<ExpressionEditorProps> = ({
    transformation,
    sourceDataModelId,
    preloadedSourceModel,
    targetJsonataPath,
    onSave,
    onCancel,
    targetJsonSchema,
}) => {
    useEffect(() => {
        if (targetJsonSchema) {
            // Temporary: just log schema as requested
            // eslint-disable-next-line no-console
            console.log('Target JSON Schema:', targetJsonSchema);
        }
    }, [targetJsonSchema]);
    const initialExpr = transformation.Expression || '';
    const [expression, setExpression] = useState<string>(initialExpr);
    // Force JSONata going forward
    const expressionLanguage = 'JSONata';
    const [name, setName] = useState<string>(transformation.Name || '');
    // Reversible removed per requirements
    const [filter, setFilter] = useState<string>('');
    const [activeElementCategory, setActiveElementCategory] =
        useState<string>('All');
    const [sampleModel, setSampleModel] =
        useState<DataModelWithDetailsWithTree | null>(null);
    const [sampleRecord, setSampleRecord] = useState<any | null>(null);
    const [previewResult, setPreviewResult] = useState<any>(null);
    const [previewError, setPreviewError] = useState<string | null>(null);
    const [loadingSample, setLoadingSample] = useState<boolean>(false);

    // Placeholder values removed – only show real schema/functions/locals now

    const filteredFunctions = useMemo(() => {
        const f = filter.toLowerCase();
        return COMMON_FUNCTIONS.filter(fn => !f || fn.label.toLowerCase().includes(f) || fn.description.toLowerCase().includes(f));
    }, [filter]);

    // Derive locals from current expression (variables assigned with :=)
    const localVariables = useMemo(() => {
        if (!expression) return [] as string[];
        const re = /\$([A-Za-z_][A-Za-z0-9_]*)\s*:=/g;
        const found = new Set<string>();
        let m: RegExpExecArray | null;
        while ((m = re.exec(expression)) !== null) {
            found.add(`$${m[1]}`);
        }
        return Array.from(found).sort();
    }, [expression]);
    const filteredLocals = useMemo(() => {
        if (!filter) return localVariables;
        const f = filter.toLowerCase();
        return localVariables.filter(l => l.toLowerCase().includes(f));
    }, [filter, localVariables]);

    // Build input schema attribute paths from the sample model's EntityTree
    const inputSchemaPaths = useMemo(() => {
        if (!sampleModel?.EntityTree) return [] as string[];
        const paths: string[] = [];
        const safeSeg = (seg: string) =>
            /^[A-Za-z_][A-Za-z0-9_]*$/.test(seg)
                ? seg
                : `["${seg.replace(/"/g, '\"')}"]`;
        const walk = (node: any, ancestors: string[]) => {
            const wrapper: any = node.Entity;
            const meta = wrapper?.Entity?.Id ? wrapper.Entity : wrapper;
            const entityName = meta?.Name || meta?.UniqueName || `Entity_${node.EntityId}`;
            const entityAncestors = [...ancestors, entityName];
            (wrapper.Attributes || []).forEach((attr: any) => {
                const segs = [...entityAncestors, attr.Name || attr.UniqueName || `attr_${attr.Id}`];
                const expr = segs.map(safeSeg).join('.');
                paths.push(expr);
            });
            (node.Children || []).forEach((child: any) => walk(child, entityAncestors));
        };
        sampleModel.EntityTree.forEach(root => walk(root, []));
        return paths.sort();
    }, [sampleModel]);

    const filteredInputSchemaPaths = useMemo(() => {
        if (!filter) return inputSchemaPaths;
        const f = filter.toLowerCase();
        return inputSchemaPaths.filter(p => p.toLowerCase().includes(f));
    }, [filter, inputSchemaPaths]);

    const textareaRef = useRef<HTMLTextAreaElement | null>(null);

    const handleInsert = useCallback((token: string, opts?: { type?: 'function' }) => {
        setExpression(prev => {
            const el = textareaRef.current;
            if (!el) {
                return prev ? prev + ' ' + token : token;
            }
            const start = el.selectionStart ?? prev.length;
            const end = el.selectionEnd ?? prev.length;
            const hasSelection = start !== end;
            let before = prev.slice(0, start);
            let selected = prev.slice(start, end);
            let after = prev.slice(end);
            let insertion = token;

            if (opts?.type === 'function' && hasSelection && selected.trim().length) {
                // Wrap selection inside function call – replace trailing () if present
                if (token.endsWith('()')) {
                    insertion = token.slice(0, -2) + '(' + selected + ')';
                } else {
                    const firstParens = token.indexOf('()');
                    if (firstParens >= 0) {
                        insertion = token.replace('()', '(' + selected + ')');
                    } else if (/\)$/.test(token)) {
                        // ends with ) but no (), just append selection inside new parens
                        insertion = token.replace(/\)$/, '(' + selected + ')');
                    } else {
                        insertion = token + '(' + selected + ')';
                    }
                }
                // Remove original selected text (already captured in before/after composition)
                selected = '';
            } else if (!hasSelection) {
                // Plain insertion at caret – add space if needed
                const needSpace = before && !/\s$/.test(before);
                if (needSpace) insertion = ' ' + insertion;
            } else {
                // Replacing selection with token (non-function or empty selection for function)
                // Keep spaces around if needed
                const needLeadingSpace = before && !/\s$/.test(before);
                const needTrailingSpace = after && !/^\s/.test(after);
                insertion = (needLeadingSpace ? ' ' : '') + insertion + (needTrailingSpace ? ' ' : '');
                selected = '';
            }

            const newValue = before + insertion + selected + after;

            // After state update, restore caret after inserted text
            requestAnimationFrame(() => {
                if (textareaRef.current) {
                    const caretPos = before.length + insertion.length;
                    textareaRef.current.focus();
                    textareaRef.current.selectionStart = caretPos;
                    textareaRef.current.selectionEnd = caretPos;
                }
            });
            return newValue;
        });
    }, []);

    const handleSave = useCallback(() => {
        onSave({
            expression,
            expressionLanguage,
            name: name || transformation.Name,
        });
    }, [expression, expressionLanguage, name, onSave, transformation.Name]);

    // No longer auto-prefill with target path assignment.

    // Load sample model + create one sample record when component mounts or model id changes
    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            // If we have preloaded model, just use it
            if (preloadedSourceModel) {
                setSampleModel(preloadedSourceModel);
                if (preloadedSourceModel.EntityTree) {
                    const sample = generateSampleRecords(
                        preloadedSourceModel,
                        preloadedSourceModel.EntityTree,
                        3
                    );
                    setSampleRecord(sample);
                }
                return;
            }
            if (!sourceDataModelId) return;
            try {
                setLoadingSample(true);
                const details = await getModelDetailsWithTree(
                    sourceDataModelId,
                    'include_entities=true'
                );
                if (cancelled) return;
                setSampleModel(details);
                if (details.EntityTree) {
                    const sample = generateSampleRecords(
                        details,
                        details.EntityTree,
                        1
                    );
                    setSampleRecord(sample);
                }
            } catch (e: any) {
                if (!cancelled) setPreviewError('Failed to load sample data');
            } finally {
                if (!cancelled) setLoadingSample(false);
            }
        };
        load();
        return () => {
            cancelled = true;
        };
    }, [sourceDataModelId, preloadedSourceModel]);

    // Evaluate JSONata expression on sampleRecord (no implicit target wrapping)
    useEffect(() => {
        let cancelled = false;
        const evaluateExpr = async () => {
            if (!sampleRecord) {
                setPreviewResult(null);
                return;
            }
            if (!expression) {
                setPreviewResult(undefined);
                return;
            }
            try {
                let evalRecord = sampleRecord;
                try {
                    const rootKeys = Object.keys(sampleRecord);
                    if (rootKeys.length === 1) {
                        const onlyKey = rootKeys[0];
                        if (
                            /[^A-Za-z0-9_]/.test(onlyKey) &&
                            typeof sampleRecord[onlyKey] === 'object'
                        ) {
                            evalRecord = sampleRecord[onlyKey];
                        }
                    }
                } catch {
                    /* ignore */
                }

                const exprText = expression.trim();
                let value: any;
                if (exprText) {
                    const expr = jsonata(exprText);
                    value = expr.evaluate(evalRecord);
                    if (value && typeof (value as any).then === 'function') {
                        value = await value;
                    }
                    if (value === undefined) {
                        const simplePathMatch =
                            /^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$/.test(exprText);
                        if (simplePathMatch) {
                            const manual = exprText
                                .split('.')
                                .reduce(
                                    (acc: any, seg: string) =>
                                        acc && typeof acc === 'object'
                                            ? acc[seg]
                                            : undefined,
                                    evalRecord
                                );
                            if (manual === undefined) {
                                setPreviewError(
                                    `Path '${exprText}' not found in sample (root keys: ${Object.keys(
                                        evalRecord
                                    ).join(', ')})`
                                );
                            }
                        }
                    }
                } else {
                    value = undefined;
                }
                if (cancelled) return;
                setPreviewResult(value);
                if (!previewError || !previewError.startsWith('Path ')) {
                    setPreviewError(null);
                }
            } catch (err: any) {
                if (cancelled) return;
                setPreviewError(err?.message || 'Expression error');
                setPreviewResult(null);
            }
        };
        evaluateExpr();
        return () => {
            cancelled = true;
        };
    }, [expression, sampleRecord]);

    return (
        <div className="expr-editor">
            <header className="expr-editor__header">
                <div className="expr-editor__title">Expression:</div>
            </header>
            <div className="expr-editor__form-row">
                <div className="expr-editor__field-group">
                    <label className="expr-editor__label">
                        Expression Language
                    </label>
                    <div className="expr-editor__readonly">JSONata</div>
                </div>
                <div className="expr-editor__field-group expr-editor__field-group--grow">
                    <label className="expr-editor__label">Column name*</label>
                    <input
                        className="expr-editor__input"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Column / transformation name"
                        spellCheck={false}
                        autoComplete="off"
                        autoCorrect="off"
                        autoCapitalize="off"
                    />
                </div>
            </div>
            <div className="expr-editor__field-group">
                <label className="expr-editor__label">Expression</label>
                <textarea
                    className="expr-editor__textarea"
                    rows={5}
                    value={expression}
                    onChange={(e) => setExpression(e.target.value)}
                    placeholder="Enter expression..."
                    spellCheck={false}
                    autoComplete="off"
                    autoCorrect="off"
                    autoCapitalize="off"
                    ref={textareaRef}
                />
            </div>
            <div className="expr-editor__operators-bar">
                {OPERATORS.map((op) => (
                    <button
                        key={op}
                        type="button"
                        className="expr-editor__op-btn"
                        onClick={() => handleInsert(op)}
                    >
                        {op}
                    </button>
                ))}
            </div>
            <div className="expr-editor__panes">
                <div className="expr-editor__elements-pane">
                    <div className="expr-editor__elements-header">
                        Expression elements
                    </div>
                    <ul className="expr-editor__elements-list">
                        {[
                            'All',
                            'Functions',
                            'Input schema',
                            'Parameters',
                            'Locals',
                        ].map((cat) => (
                            <li
                                key={cat}
                                className={
                                    cat === activeElementCategory
                                        ? 'active'
                                        : ''
                                }
                                onClick={() => setActiveElementCategory(cat)}
                            >
                                {cat}
                            </li>
                        ))}
                    </ul>
                </div>
                <div className="expr-editor__values-pane">
                    <div className="expr-editor__values-header-row">
                        <input
                            type="text"
                            className="expr-editor__filter"
                            placeholder="Filter by keyword"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                        />
                        <div className="expr-editor__create-wrapper">
                            <button
                                type="button"
                                className="expr-editor__create-btn"
                                onClick={() => window.open('https://docs.jsonata.org/overview', '_blank', 'noopener,noreferrer')}
                                title="Open JSONata documentation in a new tab"
                            >
                                JSONata Help
                            </button>
                        </div>
                    </div>
                    <div className="expr-editor__values-list">
                        {activeElementCategory === 'Input schema' ? (
                            filteredInputSchemaPaths.length ? (
                                filteredInputSchemaPaths.map(p => (
                                    <div
                                        key={p}
                                        className="expr-editor__value-item"
                                        title="Insert attribute path"
                                        onClick={() => handleInsert(p)}
                                    >
                                        {p}
                                    </div>
                                ))
                            ) : (
                                <div className="expr-editor__empty">
                                    {sampleModel ? 'No matching attributes' : 'Load or select a source model to view schema'}
                                </div>
                            )
                        ) : activeElementCategory === 'Functions' ? (
                            filteredFunctions.length ? (
                filteredFunctions.map(fn => (
                                    <div
                                        key={fn.label}
                                        className="expr-editor__value-item"
                                        title={fn.description}
                    onClick={() => handleInsert(fn.snippet, { type: 'function' })}
                                    >
                                        {fn.label}
                                    </div>
                                ))
                            ) : (
                                <div className="expr-editor__empty">No functions</div>
                            )
                        ) : activeElementCategory === 'Parameters' ? (
                            <div className="expr-editor__empty">No parameters defined</div>
                        ) : activeElementCategory === 'Locals' ? (
                            filteredLocals.length ? (
                                filteredLocals.map(loc => (
                                    <div
                                        key={loc}
                                        className="expr-editor__value-item"
                                        title="Insert local variable"
                                        onClick={() => handleInsert(loc)}
                                    >{loc}</div>
                                ))
                            ) : (
                                <div className="expr-editor__empty">No locals in expression</div>
                            )
                        ) : activeElementCategory === 'All' ? (
                            (() => {
                                type Item = { key: string; display: string; insert: string; title?: string };
                                const functionItems: Item[] = filteredFunctions.map(fn => ({ key: fn.label, display: fn.label, insert: fn.snippet, title: fn.description }));
                                const schemaItems: Item[] = filteredInputSchemaPaths.map(p => ({ key: `schema:${p}`, display: p, insert: p }));
                                const localItems: Item[] = filteredLocals.map(l => ({ key: `local:${l}`, display: l, insert: l }));
                                const all: Item[] = [...schemaItems, ...functionItems, ...localItems];
                                if (!all.length) return <div className="expr-editor__empty">No values</div>;
                return all.map(item => (
                                    <div
                                        key={item.key}
                                        className="expr-editor__value-item"
                                        title={item.title || 'Insert'}
                    onClick={() => handleInsert(item.insert, { type: functionItems.some(f => f.key === item.key) ? 'function' : undefined })}
                                    >{item.display}</div>
                                ));
                            })()
                        ) : null}
                    </div>
                </div>
            </div>
            <div className="expr-editor__preview">
                <div className="expr-editor__preview-header">
                    Preview (sample record {loadingSample ? 'loading…' : ''})
                </div>
                <div className="expr-editor__preview-body">
                    <div className="expr-editor__preview-sample">
                        <div className="expr-editor__preview-label">
                            Input sample:
                        </div>
                        <pre className="expr-editor__preview-json">
                            {sampleRecord
                                ? JSON.stringify(sampleRecord, null, 2)
                                : loadingSample
                                ? 'Loading…'
                                : 'No sample'}
                        </pre>
                    </div>
                    <div className="expr-editor__preview-result">
                        <div className="expr-editor__preview-label">
                            Result:
                        </div>
                        {previewError ? (
                            <pre className="expr-editor__preview-error">
                                {previewError}
                            </pre>
                        ) : (
                            <pre className="expr-editor__preview-json">
                                {previewResult === undefined
                                    ? 'Enter an expression to see output'
                                    : JSON.stringify(previewResult, null, 2)}
                            </pre>
                        )}
                    </div>
                </div>
            </div>
            <div className="expr-editor__footer">
                <div className="expr-editor__actions">
                    <button
                        type="button"
                        className="expr-editor__btn expr-editor__btn--secondary"
                        onClick={onCancel}
                    >
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="expr-editor__btn expr-editor__btn--primary"
                        onClick={handleSave}
                    >
                        Save
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ExpressionEditor;
