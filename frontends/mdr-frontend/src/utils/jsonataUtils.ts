/**
 * Build a default JSONata assignment expression given source/target JSON Schemas and
 * dotted source/target attribute paths (Entity.Entity.Attribute).
 *
 * Strategy (initial heuristic):
 *  - Walk target path; create nested object/array structure using schema to decide where to place arrays.
 *  - If target root segment is an array and source root segment is also an array, map target root array
 *    from the source root array:  { "TargetRoot": SourceRoot.{ <innerObject> } }.
 *  - Additional array levels in the target path (beneath the root) are emitted as single-element arrays
 *    wrapping their child object (e.g., "Contact": [{ ... }]).
 *  - The final attribute is set to the source value expression.
 *  - When mapping root arrays, the source value expression inside the mapping body is made relative
 *    (strips the leading source root segment) so that e.g. Student.Name → Name.
 *  - If any information is missing, fall back progressively: return simple equality targetPath = sourcePath.
 */
export function buildDefaultAssignmentExpression(
    sourceSchema: any | null | undefined,
    targetSchema: any | null | undefined,
    sourcePath: string,
    targetPath: string
): string {
    if (!targetPath || !sourcePath) return '';

    const srcSegs = sourcePath.split('.').filter(Boolean);
    const tgtSegs = targetPath.split('.').filter(Boolean);
    if (!tgtSegs.length) return '';

    // Helpers to traverse schema
    const getChildSchema = (schema: any, seg: string): any | undefined => {
        if (!schema) return undefined;
        if (schema.type === 'object') return schema.properties?.[seg];
        if (schema.type === 'array') {
            const items = schema.items;
            if (items?.type === 'object') return items.properties?.[seg];
            // Arrays of primitives – no deeper objects
            return undefined;
        }
        return undefined;
    };

    const isArraySegment = (schema: any, seg: string): boolean => {
        if (!schema) return false;
        const prop = schema.properties?.[seg];
        return prop?.type === 'array';
    };

    // Determine if root segments are arrays
    const targetRootIsArray =
        !!targetSchema && isArraySegment(targetSchema, tgtSegs[0]);
    const sourceRootIsArray =
        !!sourceSchema && isArraySegment(sourceSchema, srcSegs[0]);

    // Traverse target segments to collect array flags (excluding root array when mapping)
    const targetArrayFlags: boolean[] = [];
    let cursor: any = targetSchema;
    for (let i = 0; i < tgtSegs.length; i++) {
        const seg = tgtSegs[i];
        const isArr = isArraySegment(cursor, seg);
        targetArrayFlags.push(isArr);
        cursor = getChildSchema(cursor, seg);
        if (isArr && cursor && cursor.type === 'array') {
            // Dive into items for next step
            cursor = cursor.items;
        }
    }

    // Build the nested object for target path AFTER the root segment (used inside mapping or root object wrapper)
    const buildInner = (startIndex: number, valueExpr: string): string => {
        // startIndex points to the first segment to include inside the object being built
        const lastIndex = tgtSegs.length - 1;
        const recur = (i: number): string => {
            const seg = tgtSegs[i];
            if (i === lastIndex) {
                // Attribute leaf
                return `"${seg}": ${valueExpr}`;
            }
            const childContent = recur(i + 1);
            const isArr = targetArrayFlags[i];
            if (isArr) {
                return `"${seg}": [{ ${childContent} }]`;
            }
            return `"${seg}": { ${childContent} }`;
        };
        return recur(startIndex);
    };

    // Source value expression (possibly relative inside mapping)
    let valueExpr = sourcePath;
    let mappingApplied = false;

    if (targetRootIsArray && sourceRootIsArray) {
        // Root mapping scenario
        mappingApplied = true;
        // Inside mapping context strip first source segment if the value refers to that branch
        if (srcSegs.length > 1) {
            valueExpr = srcSegs.slice(1).join('.');
        } else {
            // Single attribute array of primitives; value is '.' in mapping context
            valueExpr = '$'; // fall back to entire element value
        }
    }

    const rootSeg = tgtSegs[0];
    const innerStart = 0; // build entire path; mapping adjusts wrapping separately
    const fullInner = buildInner(0, valueExpr);

    if (mappingApplied) {
        // The inner builder included the root segment; we want object for inside mapping WITHOUT root seg.
        // Rebuild skipping root seg for mapping body.
        const mappingBody = buildInner(1, valueExpr);
        const bodyObject = mappingBody ? `{ ${mappingBody} }` : '{}';
        return `{ "${rootSeg}": ${
            srcSegs[0]
        }. ${'{'} ${mappingBody} ${'}'} }`.replace(/\s+{/, ' {');
    }

    // Non-mapping: compose outer object with potential arrays
    // fullInner already contains the entire nested path, but encloses root as a property; ensure braces
    return `{ ${fullInner} }`;
}

// -------------------------------------------------------------
// JSONata evaluation helpers for bulk transformation preview
// -------------------------------------------------------------
import jsonata from "jsonata";

export interface CombinedEvaluationResult {
    output: any; // merged output object
    errors: { key: string; name?: string; expression?: string; message: string }[];
}

// Lightweight expression descriptor so callers don't need TransformationData shape
export interface JsonataExpressionDescriptor {
    key: string; // unique stable key (id or index)
    name?: string; // optional display name
    expression: string; // JSONata expression text
    language?: string; // if provided and not JSONata, it's skipped
}

// Deep merge two plain objects (mutates target). Arrays & differing types override.
function deepMerge(target: any, source: any): any {
    if (target === source) return target;
    // Primitive / null or array passthrough logic handled below
    if (Array.isArray(source)) {
        if (!Array.isArray(target)) return clone(source);
        // Heuristic: if both arrays length 1 and elements are plain objects, merge their element 0 recursively
        if (source.length === 1 && target.length === 1 && isPlainObj(target[0]) && isPlainObj(source[0])) {
            deepMerge(target[0], source[0]);
            return target;
        }
        // Element-wise merge when lengths match and all elements are plain objects
        if (source.length === target.length && source.every(isPlainObj) && target.every(isPlainObj)) {
            for (let i = 0; i < source.length; i++) {
                deepMerge(target[i], source[i]);
            }
            return target;
        }
        // Fallback: concatenate (avoid duplicating identical JSON serializations)
        const existingSerialized = new Set(target.map(v => safeStringify(v)));
        source.forEach(item => {
            const ser = safeStringify(item);
            if (!existingSerialized.has(ser)) target.push(clone(item));
        });
        return target;
    }
    if (!source || typeof source !== 'object') return source;
    if (!target || typeof target !== 'object' || Array.isArray(target)) return clone(source);
    Object.keys(source).forEach(key => {
        const sv = source[key];
        if (sv === undefined) return;
        const tv = target[key];
        if (Array.isArray(sv)) {
            target[key] = deepMerge(Array.isArray(tv) ? tv : [], sv);
        } else if (isPlainObj(sv) && isPlainObj(tv)) {
            deepMerge(tv, sv);
        } else if (isPlainObj(sv) && !tv) {
            target[key] = clone(sv);
        } else if (isPlainObj(sv) && !isPlainObj(tv)) {
            target[key] = clone(sv);
        } else {
            target[key] = sv;
        }
    });
    return target;
}

function isPlainObj(v: any) { return !!v && Object.getPrototypeOf(v) === Object.prototype; }
function clone(v: any): any { return Array.isArray(v) ? v.map(clone) : (isPlainObj(v) ? Object.keys(v).reduce((a,k)=>{a[k]=clone(v[k]);return a;}, {} as any) : v); }
function safeStringify(v: any) { try { return JSON.stringify(v); } catch { return String(v); } }

/** Evaluate a single JSONata expression safely. */
export async function evaluateJsonataExpression(expression: string, input: any): Promise<any> {
    const expr = jsonata(expression);
    const val = expr.evaluate(input);
    return val && typeof (val as any).then === 'function' ? await val : val;
}

/**
 * Evaluate all transformation expressions (JSONata) and build a combined output object.
 * Rules:
 *  - Skip empty expressions or non-JSONata languages.
 *  - If expression result is an object (non-array), deep merge into accumulator.
 *  - If result is primitive / array / null, assign under a synthesized key based on transformation name or id.
 *  - Later expressions override earlier on key conflicts (except nested object merge).
 */
export async function evaluateAndCombineExpressions(
    expressions: JsonataExpressionDescriptor[],
    inputSample: any
): Promise<CombinedEvaluationResult> {
    const out: any = {};
    const errors: CombinedEvaluationResult['errors'] = [];
    for (const t of expressions) {
        const exprText = (t.expression || '').trim();
        if (!exprText) continue;
        if (t.language && t.language !== 'JSONata') continue; // only support JSONata now
        try {
            const value = await evaluateJsonataExpression(exprText, inputSample);
            if (value && typeof value === 'object' && !Array.isArray(value)) {
                deepMerge(out, value);
            } else {
                const key = t.name?.trim() || t.key;
                out[key] = value;
            }
        } catch (e: any) {
            errors.push({ key: t.key, name: t.name, expression: t.expression, message: e?.message || 'Evaluation error' });
        }
    }
    return { output: out, errors };
}

// ---------------------------------------------
// Single-pass combined expression construction
// ---------------------------------------------

/** Escape transformation name for use as a JSON object key within JSONata */
function escapeKey(name: string): string {
    // Always quote to stay safe
    return name.replace(/"/g, '\\"');
}

/**
 * Build a single JSONata expression that, when evaluated, produces the merged
 * output of all expressions. Each expression is expected to return either:
 *  - an object (already keyed) – included directly in merge list
 *  - any other value – wrapped as { "<name>": (<expr>) }
 *
 * Shallow merge only: later objects override earlier keys entirely.
 * If you need deep merge semantics, fall back to iterative evaluation.
 */
export function buildCombinedJsonataExpression(
    expressions: JsonataExpressionDescriptor[]
): { expression: string; count: number } {
    const parts: string[] = [];
    expressions.forEach(e => {
        if (!e || e.language && e.language !== 'JSONata') return;
        const expr = (e.expression || '').trim();
        if (!expr) return;
        const name = e.name?.trim() || e.key;
        // Heuristic: treat as object if starts with '{' (ignoring leading parens) and ends with '}'
        const looksObject = /^{/.test(expr.replace(/^\(/, '').trim()) && /}$/.test(expr.replace(/\)$/, '').trim());
        if (looksObject) {
            parts.push(expr);
        } else {
            parts.push(`{ "${escapeKey(name)}": (${expr}) }`);
        }
    });
    if (!parts.length) return { expression: 'null', count: 0 };
    // Use $merge for shallow merge
    const merged = parts.length === 1 ? parts[0] : `$merge([ ${parts.join(', ')} ])`;
    return { expression: merged, count: parts.length };
}

export async function evaluateCombinedJsonataExpression(
    combined: { expression: string; count: number },
    input: any
): Promise<any> {
    if (!combined.count) return null;
    const expr = jsonata(combined.expression);
    const res = expr.evaluate(input);
    return res && typeof (res as any).then === 'function' ? await res : res;
}


/**
 * Quote one path segment so it reads that field in a JSONata path expression.
 * JSONata quotes field names with backticks; `["name"]` would be an array literal.
 * A backtick cannot be escaped inside backticks, so those names fall back to $lookup.
 */
export function quoteJsonataSegment(seg: string): string {
    if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(seg)) return seg;
    if (!seg.includes("`")) return `\`${seg}\``;
    return `$lookup($, ${JSON.stringify(seg)})`;
}
