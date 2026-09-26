import { describe, it, expect } from 'vitest';
import { validateAgainstSchema } from './schemaValidation';

/** Shaped like what `generateJsonSchema` emits: draft 2020-12, strict objects, required list. */
const schema = {
    $schema: 'https://json-schema.org/draft/2020-12/schema',
    type: 'object',
    additionalProperties: false,
    required: ['Person'],
    properties: {
        Person: {
            type: 'object',
            additionalProperties: false,
            required: ['givenName', 'familyName'],
            properties: {
                givenName: { type: 'string' },
                familyName: { type: 'string' },
                birthDate: { type: 'string', format: 'date' },
                identifierType: { type: 'string', enum: ['School-assigned number', 'National ID'] },
            },
        },
    },
};

describe('validateAgainstSchema', () => {
    it('reports nothing when there is no target schema', () => {
        expect(validateAgainstSchema({ anything: 1 }, null).issues).toEqual([]);
        expect(validateAgainstSchema({ anything: 1 }, undefined).issues).toEqual([]);
    });

    it('reports nothing when there is no output yet', () => {
        expect(validateAgainstSchema(null, schema).issues).toEqual([]);
        expect(validateAgainstSchema(undefined, schema).issues).toEqual([]);
    });

    it('accepts conforming output', () => {
        const output = { Person: { givenName: 'Ada', familyName: 'Lovelace' } };
        expect(validateAgainstSchema(output, schema).issues).toEqual([]);
    });

    it('reports a type mismatch against the offending path', () => {
        const output = { Person: { givenName: 42, familyName: 'Lovelace' } };
        const { issues } = validateAgainstSchema(output, schema);
        expect(issues).toHaveLength(1);
        expect(issues[0].keyword).toBe('type');
        expect(issues[0].path).toBe('/Person/givenName');
        expect(issues[0].message).toMatch(/must be string/);
    });

    it('reports an enum violation, which is how a casing mistake surfaces', () => {
        const output = {
            Person: { givenName: 'Ada', familyName: 'Lovelace', identifierType: 'school-assigned number' },
        };
        const { issues } = validateAgainstSchema(output, schema);
        expect(issues).toHaveLength(1);
        expect(issues[0].keyword).toBe('enum');
        expect(issues[0].path).toBe('/Person/identifierType');
    });

    it('names the offending key on an unexpected property', () => {
        const output = { Person: { givenName: 'Ada', familyName: 'Lovelace', nickname: 'Ada' } };
        const { issues } = validateAgainstSchema(output, schema);
        expect(issues).toHaveLength(1);
        expect(issues[0].keyword).toBe('additionalProperties');
        expect(issues[0].message).toBe('has unexpected property "nickname"');
    });

    it('suppresses missing-required errors by default, because the preview is partial', () => {
        const output = { Person: { givenName: 'Ada' } }; // familyName not mapped yet
        expect(validateAgainstSchema(output, schema).issues).toEqual([]);
    });

    it('reports missing-required errors when completeness is requested', () => {
        const output = { Person: { givenName: 'Ada' } };
        const { issues } = validateAgainstSchema(output, schema, { includeRequired: true });
        expect(issues).toHaveLength(1);
        expect(issues[0].keyword).toBe('required');
        expect(issues[0].message).toBe('is missing required property "familyName"');
    });

    it('suppresses required errors but keeps real violations in the same output', () => {
        const output = { Person: { givenName: 42 } }; // wrong type AND missing familyName
        const { issues } = validateAgainstSchema(output, schema);
        expect(issues).toHaveLength(1);
        expect(issues[0].keyword).toBe('type');
    });

    it('does NOT validate format, matching the runtime translator', () => {
        // The translator calls jsonschema.validate() with no format_checker, so a malformed date
        // is accepted at runtime. Flagging it here would make the UI stricter than the thing it
        // is predicting. If this test starts failing, ajv-formats was added — that is a product
        // decision, not a bug fix.
        const output = { Person: { givenName: 'Ada', familyName: 'Lovelace', birthDate: 'not-a-date' } };
        expect(validateAgainstSchema(output, schema).issues).toEqual([]);
    });

    it('surfaces a schema that cannot be compiled instead of throwing', () => {
        const broken = { $schema: 'https://json-schema.org/draft/2020-12/schema', type: 'not-a-type' };
        const result = validateAgainstSchema({ a: 1 }, broken);
        expect(result.schemaError).toBeTruthy();
        expect(result.issues).toEqual([]);
    });
});
