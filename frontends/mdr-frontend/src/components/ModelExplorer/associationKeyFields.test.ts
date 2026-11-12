import { describe, it, expect } from "vitest";

import {
    associationArrayCreateFields,
    associationKeyFields,
    entityAssociationFields,
    toAssociationUpdate,
    withCreateArray,
    withSelectedArray,
} from "./CreateOptFields";

const names = (fields: { name: string }[]) => fields.map((f) => f.name);

const ownModel = { Id: 20, Type: "SourceSchema", BaseDataModelId: null };
const overlay = { Id: 17, Type: "OrgLIF", BaseDataModelId: 1 };

describe("editing an association's Name and Array (#1472)", () => {
    it("offers both in the edit dialog", () => {
        expect(names(associationKeyFields())).toEqual(["Name", "Array"]);
        expect(names(entityAssociationFields({}))).not.toContain("Name");
    });

    it("sends a cleared Name as null, which resets it to the default key", () => {
        expect(toAssociationUpdate({ Name: "", Notes: "n" })).toEqual({ Name: null, Notes: "n" });
    });

    it("leaves every other edit as it is", () => {
        expect(toAssociationUpdate({ Name: "Studies", Array: false })).toEqual({ Name: "Studies", Array: false });
        expect(toAssociationUpdate({ Notes: "n" })).toEqual({ Notes: "n" });
        // Whitespace is left for the API to refuse, so the user sees why.
        expect(toAssociationUpdate({ Name: "  " })).toEqual({ Name: "  " });
    });
});

describe("creating an association with an Array (#1472)", () => {
    it("offers Array, but not Name, in a model's own create dialog", () => {
        expect(names(associationArrayCreateFields(ownModel))).toEqual(["Array"]);
    });

    it("leaves Array to the API in an overlay, whose cross-model associations can't set it", () => {
        expect(associationArrayCreateFields(overlay)).toEqual([]);
        // No Array field, so picking a child and creating never send one.
        const params = withSelectedArray({ Array: "Yes" }, { Notes: null });
        expect(params).toEqual({ Notes: null });
        expect(withCreateArray({ EntityId: 5 }, params)).toEqual({ EntityId: 5 });
    });

    it("starts Array at the picked child's own setting", () => {
        expect(withSelectedArray({ Array: "Yes" }, { Array: null, Placement: "Embedded" }).Array).toBe(true);
        expect(withSelectedArray({ Array: "No" }, { Array: true, Placement: "Embedded" }).Array).toBe(false);
        expect(withSelectedArray({ Array: "Yes" }, { Array: null }).Array).toBe(true); // an attribute
    });

    it("starts a Reference single, whatever its child (#1471)", () => {
        expect(withSelectedArray({ Array: "Yes" }, { Array: null, Placement: "Reference" }).Array).toBe(false);
    });

    it("sends a false Array, which the create template would drop", () => {
        expect(withCreateArray({ EntityId: 5, Notes: null }, { Array: false })).toEqual({
            EntityId: 5,
            Notes: null,
            Array: false,
        });
        expect(withCreateArray({ EntityId: 5 }, { Array: true }).Array).toBe(true);
    });
});
