/**
 * Validate assembled transformation output against a target LIF JSON Schema.
 *
 * The runtime translator validates the same way (`jsonschema.validate` in
 * `components/lif/translator/core.py`); this brings that check forward into the authoring UI.
 *
 * Two deliberate choices keep the UI's verdict aligned with what the translator actually does:
 *
 *  - **Draft 2020-12.** `generateJsonSchema` emits `$schema: .../draft/2020-12/schema`, so the
 *    `Ajv2020` entry point is required. Ajv's default export is draft-07 and rejects it.
 *  - **`format` is not validated.** The translator calls `validate()` without a `format_checker`,
 *    and Python's `jsonschema` treats `format` as an annotation by default. Adding `ajv-formats`
 *    here would reject data the translator accepts.
 *
 * `required` errors are filtered out unless asked for, because the preview output is intentionally
 * partial — an author previewing three attributes of a large model would otherwise see an error for
 * every attribute they have not mapped yet.
 */
import Ajv2020 from 'ajv/dist/2020';
import type { ErrorObject, ValidateFunction } from 'ajv';

export interface SchemaValidationIssue {
    /** Instance location of the problem, e.g. "/Person/0/givenName". Empty string means the root. */
    path: string;
    /** Ajv keyword that failed, e.g. "type", "enum", "additionalProperties", "required". */
    keyword: string;
    /** Human-readable message, e.g. "must be string". */
    message: string;
}

export interface SchemaValidationResult {
    issues: SchemaValidationIssue[];
    /** Set when the target schema itself could not be compiled; issues will be empty. */
    schemaError?: string;
}

export interface SchemaValidationOptions {
    /**
     * Include "missing required property" errors. Off by default: the preview is a partial
     * document, so required errors describe work not yet done rather than output that is wrong.
     */
    includeRequired?: boolean;
}

const EMPTY: SchemaValidationResult = { issues: [] };

// Compiling a full LIF schema is not cheap and the preview re-evaluates on every edit, so hold
// compiled validators per schema object. Schema identity is stable across renders (it is React
// state), and a WeakMap lets a replaced schema be collected.
const compiledCache = new WeakMap<object, ValidateFunction | string>();

function getValidator(schema: object): ValidateFunction | string {
    const cached = compiledCache.get(schema);
    if (cached) return cached;
    let result: ValidateFunction | string;
    try {
        // strict: false — schemas are generated from MDR models and may carry annotations Ajv's
        // strict mode would reject outright; we want data errors, not schema-authoring complaints.
        const ajv = new Ajv2020({ allErrors: true, strict: false });
        result = ajv.compile(schema);
    } catch (e) {
        result = (e instanceof Error && e.message) || 'Target schema could not be compiled';
    }
    compiledCache.set(schema, result);
    return result;
}

function toIssue(err: ErrorObject): SchemaValidationIssue {
    const base = {
        path: err.instancePath || '',
        keyword: err.keyword,
        message: err.message || 'is invalid',
    };
    // Ajv reports the offending key in params rather than the path for these two, so fold it into
    // the message — otherwise every such error reads identically and points at the parent object.
    if (err.keyword === 'additionalProperties') {
        const prop = (err.params as { additionalProperty?: string })?.additionalProperty;
        if (prop) return { ...base, message: `has unexpected property "${prop}"` };
    }
    if (err.keyword === 'required') {
        const prop = (err.params as { missingProperty?: string })?.missingProperty;
        if (prop) return { ...base, message: `is missing required property "${prop}"` };
    }
    return base;
}

/**
 * Validate `output` against `schema`.
 *
 * Returns no issues when either argument is absent, so a missing target schema degrades to "no
 * validation" rather than to a false all-clear or an error.
 */
export function validateAgainstSchema(
    output: unknown,
    schema: any | null | undefined,
    options: SchemaValidationOptions = {}
): SchemaValidationResult {
    if (!schema || typeof schema !== 'object') return EMPTY;
    if (output === null || output === undefined) return EMPTY;

    const validator = getValidator(schema);
    if (typeof validator === 'string') return { issues: [], schemaError: validator };

    const valid = validator(output);
    if (valid || !validator.errors) return EMPTY;

    const issues = validator.errors
        .filter(err => options.includeRequired || err.keyword !== 'required')
        .map(toIssue);

    return { issues };
}
