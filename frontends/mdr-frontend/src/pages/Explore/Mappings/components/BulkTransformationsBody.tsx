import React, { useMemo, useState, useCallback } from 'react';
import type { TransformationGroupDetails, TransformationData } from '../../../../services/transformationsService';
import './BulkTransformationsBody.css';
import { generateSampleDataFromSchema } from '../../../../services/modelService';
import { evaluateAndCombineExpressions } from '../../../../utils/jsonataUtils';
import { validateAgainstSchema } from '../../../../utils/schemaValidation';

export interface BulkTransformationsBodyProps {
  group: TransformationGroupDetails | null;
  transformations: TransformationData[];
  selected: TransformationData | null;
  onSelect: (id: number | null) => void;
  sourceSchema?: any; // JSON Schema for source model
  targetSchema?: any; // JSON Schema for target model (reserved for future use)
  onPendingDeletesChange?: (ids: number[]) => void; // notify parent when pending deletions change
  onPendingEditsChange?: (edits: { id: number; expression: string }[]) => void; // notify parent when pending expression edits change
}

// Simple preview placeholders; we'll flesh out evaluation, editing, and diffing in later steps.
const BulkTransformationsBody: React.FC<BulkTransformationsBodyProps> = ({ group, transformations, selected, onSelect, sourceSchema, targetSchema, onPendingDeletesChange, onPendingEditsChange }) => {
  const ordered = useMemo(() => transformations.slice().sort((a, b) => (a.Name || '').localeCompare(b.Name || '')), [transformations]);

  // Allow user to choose how many sample records to generate (1-20)
  const [sampleCount, setSampleCount] = useState<number>(2);
  // Input data mode: generated from schema or user-uploaded JSON
  const [inputDataMode, setInputDataMode] = useState<'generated' | 'uploaded'>('generated');
  const [uploadedJson, setUploadedJson] = useState<any | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const onChangeSampleCount = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = parseInt(e.target.value, 10);
    if (isNaN(raw)) return; // ignore invalid
    const clamped = Math.max(1, Math.min(20, raw));
    setSampleCount(clamped);
  }, []);

  const sampleInput = useMemo(() => {
    if (inputDataMode === 'uploaded') return uploadedJson;
    if (!sourceSchema) return null;
    try {
      return generateSampleDataFromSchema(sourceSchema, { arrayCount: sampleCount });
    } catch {
      return null;
    }
  }, [sourceSchema, sampleCount, inputDataMode, uploadedJson]);
  const [combinedOutput, setCombinedOutput] = useState<any | null>(null);
  // Map of expression key -> error message
  const [errorMap, setErrorMap] = useState<Record<string, string>>({});
  // Track which card's error detail is expanded
  const [expandedErrorKey, setExpandedErrorKey] = useState<string | null>(null);
  // Track hidden (inactive) expression ids (string keys)
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());
  // Track soft-deleted expression ids
  const [deletedKeys, setDeletedKeys] = useState<Set<string>>(new Set());
  // Track editing state (which items are expanded for editing)
  const [editingKeys, setEditingKeys] = useState<Set<string>>(new Set());
  // Map of id -> edited expression value (only when changed from original)
  const [editedExpressions, setEditedExpressions] = useState<Map<number, string>>(new Map());

  // View modes: 'data' (sample / output preview) or 'schema'
  const [inputViewMode, setInputViewMode] = useState<'data' | 'schema'>('data');
  const [outputViewMode, setOutputViewMode] = useState<'data' | 'schema'>('data');
  // Off by default: the preview is a partial document, so missing-required errors would
  // otherwise report every attribute the author has not mapped yet.
  const [checkCompleteness, setCheckCompleteness] = useState(false);

  // Evaluate all transformations; suspended while any editor is open.
  React.useEffect(() => {
    // Don't re-evaluate while user is actively editing (avoid running on every keystroke)
    if (editingKeys.size > 0) return; // resume once all editors closed
    let cancelled = false;
    const run = async () => {
      if (!sampleInput) { setCombinedOutput(null); setErrorMap({}); return; }
      try {
        const descriptors = transformations
          .filter(t => !hiddenKeys.has(String(t.Id)) && !deletedKeys.has(String(t.Id)))
          .map(t => {
            const edited = editedExpressions.get(t.Id);
            const baseExpr = t.Expression || '';
            const useExpr = (edited != null && edited !== baseExpr) ? edited : baseExpr;
            return {
              key: String(t.Id),
              name: t.Name,
              expression: useExpr,
              language: t.ExpressionLanguage as any,
            };
          });
        const iter = await evaluateAndCombineExpressions(descriptors, sampleInput);
        const output = iter.output;
        const newErrorMap: Record<string, string> = {};
        if (iter.errors.length) {
          iter.errors.forEach(e => { newErrorMap[e.key] = e.message; });
        }
        if (cancelled) return;
        setCombinedOutput(output);
        setErrorMap(newErrorMap);
        if (expandedErrorKey && !newErrorMap[expandedErrorKey]) setExpandedErrorKey(null);
      } catch (e:any) {
        if (cancelled) return;
        setCombinedOutput(null);
        setErrorMap({ __global: e?.message || 'Evaluation failure' });
      }
    };
    run();
    return () => { cancelled = true; };
  }, [sampleInput, transformations, hiddenKeys, deletedKeys, editingKeys.size, editedExpressions, expandedErrorKey]);

  const schemaValidation = useMemo(
    () => validateAgainstSchema(combinedOutput, targetSchema, { includeRequired: checkCompleteness }),
    [combinedOutput, targetSchema, checkCompleteness]
  );

  const totalErrors = Object.keys(errorMap).length;
  const hiddenCount = hiddenKeys.size;
  const deletedCount = deletedKeys.size;
  const editedCount = useMemo(() => {
    let c = 0;
    for (const [id, val] of editedExpressions.entries()) {
      const orig = transformations.find(t => t.Id === id)?.Expression || '';
      if (val !== orig && !deletedKeys.has(String(id))) c += 1;
    }
    return c;
  }, [editedExpressions, transformations, deletedKeys]);
  const toggleErrorExpand = (key: string) => {
    setExpandedErrorKey(prev => prev === key ? null : key);
  };
  const toggleHidden = (key: string) => {
    setHiddenKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };
  const toggleDeleted = (key: string, idNum: number) => {
    setDeletedKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };
  const toggleEditing = (key: string, idNum: number, currentExpression: string) => {
    setEditingKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
    // Initialize editedExpressions map with original value if entering edit mode and not present
    setEditedExpressions(prev => {
      if (!prev.has(idNum)) {
        const next = new Map(prev);
        next.set(idNum, currentExpression || '');
        return next;
      }
      return prev;
    });
  };
  const updateEditedExpression = (id: number, value: string) => {
    setEditedExpressions(prev => {
      const next = new Map(prev);
      next.set(id, value);
      return next;
    });
  };

  // Notify parent of pending deletes after state commit to avoid updating parent during render
  React.useEffect(() => {
    if (!onPendingDeletesChange) return;
    const ids = Array.from(deletedKeys).map(k => Number(k)).filter(n => !Number.isNaN(n));
    onPendingDeletesChange(ids);
  }, [deletedKeys, onPendingDeletesChange]);
  // Notify parent of pending edits (only those changed from original)
  React.useEffect(() => {
    if (!onPendingEditsChange) return;
    const edits: { id: number; expression: string }[] = [];
    editedExpressions.forEach((val, id) => {
      const orig = transformations.find(t => t.Id === id)?.Expression || '';
      if (val !== orig && !deletedKeys.has(String(id))) edits.push({ id, expression: val });
    });
    onPendingEditsChange(edits);
  }, [editedExpressions, transformations, deletedKeys, onPendingEditsChange]);
  return (
    <div className="bulk-body">
      {/* Row 1: transformation cards list */}
      <div className="bulk-body__row bulk-body__row--cards">
        <div className="bulk-body__cards-scroll">
          {ordered.map(t => {
            const key = String(t.Id);
            const err = errorMap[key];
            const hasError = !!err;
            const expanded = expandedErrorKey === key;
            const isHidden = hiddenKeys.has(key);
            const isDeleted = deletedKeys.has(key);
            const isEditing = editingKeys.has(key);
            const editedValue = editedExpressions.get(t.Id);
            const originalExpr = t.Expression || '';
            const isDirty = editedValue != null && editedValue !== originalExpr && !isDeleted;
            return (
              <div key={key} className={"bulk-xform-card-wrapper" + (hasError ? ' bulk-xform-card-wrapper--error' : '') + (isHidden ? ' bulk-xform-card-wrapper--hidden' : '') + (isDeleted ? ' bulk-xform-card-wrapper--deleted' : '')}>
                <div className="bulk-xform-card">
                  <div className="bulk-xform-card__expr">
                    {(() => {
                      const displayExpr = (editedValue != null && editedValue !== originalExpr) ? editedValue : originalExpr;
                      if (isEditing) {
                        return (
                          <textarea
                            className="bulk-xform-card__textarea"
                            value={editedValue != null ? editedValue : originalExpr}
                            onChange={(e) => updateEditedExpression(t.Id, e.target.value)}
                            aria-label="Edit transformation expression"
                            spellCheck={false}
                            autoComplete="off"
                            autoCorrect="off"
                            autoCapitalize="off"
                          />
                        );
                      }
                      return displayExpr || <em>(empty)</em>;
                    })()}
                  </div>
                  <div className="bulk-xform-card__meta-row">
                    <div className="bulk-xform-card__meta">
                      {t.Name || <span className="bulk-xform-card__untitled">Untitled</span>}
                      {hasError && (
                        <span className="bulk-xform-card__badge" onClick={(e) => { e.stopPropagation(); toggleErrorExpand(key); }} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleErrorExpand(key); } }}>
                          Error
                        </span>
                      )}
                      {isHidden && (<span className="bulk-xform-card__badge bulk-xform-card__badge--hidden">Hidden</span>)}
                      {isDeleted && (<span className="bulk-xform-card__badge bulk-xform-card__badge--deleted">Deleted</span>)}
                      {isDirty && (<span className="bulk-xform-card__badge bulk-xform-card__badge--edited">Edited</span>)}
                    </div>
                    <div className="bulk-xform-card__actions" aria-label="Expression actions">
                      <button type="button" className={"bulk-xform-card__action-btn" + (isHidden ? ' is-active' : '')} aria-label={isHidden ? 'Show expression in evaluation' : 'Hide expression from evaluation'} onClick={(e) => { e.stopPropagation(); toggleHidden(key); }}>
                        {isHidden ? '👁️‍🗨️' : '👁'}
                      </button>
                      <button type="button" className={"bulk-xform-card__action-btn" + (isEditing ? ' is-active' : '')} aria-label={isEditing ? 'Close editor' : 'Edit expression'} onClick={(e) => { e.stopPropagation(); toggleEditing(key, t.Id, originalExpr); }}>✎</button>
                      <button type="button" className={"bulk-xform-card__action-btn" + (isDeleted ? ' is-active is-danger' : '')} aria-label={isDeleted ? 'Undo delete' : 'Mark for deletion'} onClick={(e) => { e.stopPropagation(); toggleDeleted(key, t.Id); }}>{isDeleted ? '↺' : '🗑'}</button>
                    </div>
                  </div>
                  {hasError && expanded && (
                    <div className="bulk-xform-card__error-detail" role="alert">{err}</div>
                  )}
                </div>
              </div>
            );
          })}
          {ordered.length === 0 && (
            <div className="bulk-body__empty">No transformations in this group.</div>
          )}
        </div>
        <div className="bulk-body__cards-footer" aria-label="Expressions summary">
          <span className="bulk-body__cards-count">{ordered.length} {ordered.length === 1 ? 'expression' : 'expressions'}</span>
          <span className="bulk-body__cards-sep" aria-hidden="true">•</span>
          <span className={"bulk-body__cards-errors" + (totalErrors ? ' has-errors' : '')}>{totalErrors} {totalErrors === 1 ? 'error' : 'errors'}</span>
          <span className="bulk-body__cards-sep" aria-hidden="true">•</span>
          <span className={"bulk-body__cards-hidden" + (hiddenCount ? ' has-hidden' : '')}>{hiddenCount} {hiddenCount === 1 ? 'hidden' : 'hidden'}</span>
          <span className="bulk-body__cards-sep" aria-hidden="true">•</span>
          <span className={"bulk-body__cards-deleted" + (deletedCount ? ' has-deleted' : '')}>{deletedCount} {deletedCount === 1 ? 'deleted' : 'deleted'}</span>
          <span className="bulk-body__cards-sep" aria-hidden="true">•</span>
          <span className={"bulk-body__cards-edited" + (editedCount ? ' has-edited' : '')}>{editedCount} {editedCount === 1 ? 'edited' : 'edited'}</span>
        </div>
      </div>
      {/* Row 2: IO preview columns */}
      <div className="bulk-body__row bulk-body__row--io">
        <div className="bulk-body__col bulk-body__col--input" aria-label="Input data">
          <div className="bulk-body__col-title bulk-body__col-title--with-control">
            <span>Input ({inputViewMode === 'data' ? 'Sample' : 'Schema'})</span>
            <div className="bulk-body__header-controls">
              {inputViewMode === 'data' && (
                <div className="bulk-body__input-mode-toggle" role="group" aria-label="Input data source mode">
                  <button
                    type="button"
                    className={"bulk-body__toggle-btn" + (inputDataMode === 'generated' ? ' is-active' : '')}
                    onClick={() => { setInputDataMode('generated'); setUploadError(null); }}
                  >Generated</button>
                  <button
                    type="button"
                    className={"bulk-body__toggle-btn" + (inputDataMode === 'uploaded' ? ' is-active' : '')}
                    onClick={() => {
                      setInputDataMode('uploaded');
                      const el = document.getElementById('bulk-upload-json-input') as HTMLInputElement | null;
                      el?.click();
                    }}
                  >File</button>
                </div>
              )}
              {inputViewMode === 'data' && (
                <label className="bulk-body__sample-control">
                  <span className="bulk-body__sample-control-label">Rows</span>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={sampleCount}
                    onChange={onChangeSampleCount}
                    className="bulk-body__sample-count"
                    aria-label="Number of sample records"
                    disabled={inputDataMode === 'uploaded'}
                  />
                </label>
              )}
              <div className="bulk-body__toggle" role="group" aria-label="Toggle input view">
                <button type="button" className={"bulk-body__toggle-btn" + (inputViewMode === 'data' ? ' is-active' : '')} onClick={() => setInputViewMode('data')}>Data</button>
                <button type="button" className={"bulk-body__toggle-btn" + (inputViewMode === 'schema' ? ' is-active' : '')} onClick={() => setInputViewMode('schema')}>Schema</button>
              </div>
              <input
                id="bulk-upload-json-input"
                type="file"
                accept="application/json,.json"
                className="bulk-body__file-input-hidden"
                aria-label="Upload JSON file for input data"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const reader = new FileReader();
                  reader.onload = () => {
                    try {
                      const text = String(reader.result || '');
                      const parsed = JSON.parse(text);
                      setUploadedJson(parsed);
                      setInputDataMode('uploaded');
                      setUploadError(null);
                    } catch (err:any) {
                      setUploadError('Invalid JSON file');
                      setUploadedJson(null);
                    }
                  };
                  reader.onerror = () => {
                    setUploadError('Failed to read file');
                    setUploadedJson(null);
                  };
                  reader.readAsText(file);
                  // Reset input for same file re-selection
                  e.target.value = '';
                }}
              />
            </div>
          </div>
          {inputViewMode === 'data' ? (
            group && sampleInput ? (
              <pre className="bulk-body__preview">{JSON.stringify(sampleInput, null, 2)}</pre>
            ) : group ? (
              inputDataMode === 'uploaded' ? (
                <div className="bulk-body__placeholder">{uploadError ? uploadError : 'No file loaded yet.'}</div>
              ) : (
                <div className="bulk-body__placeholder">No sample generated (missing or invalid source schema).</div>
              )
            ) : (
              <div className="bulk-body__placeholder">No group context.</div>
            )
          ) : (
            sourceSchema ? (
              <pre className="bulk-body__preview">{JSON.stringify(sourceSchema, null, 2)}</pre>
            ) : (
              <div className="bulk-body__placeholder">No source schema provided.</div>
            )
          )}
        </div>
        <div className="bulk-body__col bulk-body__col--output" aria-label="Output preview">
          <div className="bulk-body__col-title bulk-body__col-title--with-control">
            <span>Output ({outputViewMode === 'data' ? 'Preview' : 'Schema'})</span>
            <div className="bulk-body__header-controls">
              <div className="bulk-body__toggle" role="group" aria-label="Toggle output view">
                <button type="button" className={"bulk-body__toggle-btn" + (outputViewMode === 'data' ? ' is-active' : '')} onClick={() => setOutputViewMode('data')}>Data</button>
                <button type="button" className={"bulk-body__toggle-btn" + (outputViewMode === 'schema' ? ' is-active' : '')} onClick={() => setOutputViewMode('schema')}>Schema</button>
              </div>
              {outputViewMode === 'data' && targetSchema ? (
                <button
                  type="button"
                  className={"bulk-body__toggle-btn" + (checkCompleteness ? ' is-active' : '')}
                  aria-pressed={checkCompleteness}
                  title="Also report properties the target schema requires that the output does not set yet"
                  onClick={() => setCheckCompleteness(v => !v)}
                >Check completeness</button>
              ) : null}
            </div>
          </div>
          {outputViewMode === 'data' ? (
            combinedOutput ? (
              <pre className="bulk-body__preview">{JSON.stringify(combinedOutput, null, 2)}</pre>
            ) : sampleInput ? (
              <div className="bulk-body__placeholder">No output produced (expressions may be empty).</div>
            ) : (
              <div className="bulk-body__placeholder">Waiting on sample input.</div>
            )
          ) : (
            targetSchema ? (
              <pre className="bulk-body__preview">{JSON.stringify(targetSchema, null, 2)}</pre>
            ) : (
              <div className="bulk-body__placeholder">No target schema provided.</div>
            )
          )}
          {outputViewMode === 'data' && combinedOutput ? (
            schemaValidation.schemaError ? (
              <div className="bulk-body__schema-issues bulk-body__schema-issues--error">
                Target schema could not be compiled: {schemaValidation.schemaError}
              </div>
            ) : schemaValidation.issues.length ? (
              <div className="bulk-body__schema-issues">
                <div className="bulk-body__schema-issues-title">
                  {schemaValidation.issues.length} schema {schemaValidation.issues.length === 1 ? 'issue' : 'issues'}
                </div>
                <ul>
                  {schemaValidation.issues.map((issue, i) => (
                    <li key={`${issue.path}-${issue.keyword}-${i}`}>
                      <code>{issue.path || '(root)'}</code> {issue.message}
                    </li>
                  ))}
                </ul>
              </div>
            ) : targetSchema ? (
              <div className="bulk-body__schema-issues bulk-body__schema-issues--ok">
                Output conforms to the target schema{checkCompleteness ? '' : ' (completeness not checked)'}.
              </div>
            ) : null
          ) : null}
          {/* Error list removed; surfaced inline with each expression card */}
        </div>
      </div>
    </div>
  );
};

export default BulkTransformationsBody;
