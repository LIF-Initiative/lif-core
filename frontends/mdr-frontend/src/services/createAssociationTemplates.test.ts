import { describe, it, expect, vi } from "vitest";

vi.mock("./api", () => ({ default: {} }));

import { tmplCreateEntityAttributeAssociation } from "./attributesService";
import { tmplCreateEntityAssociation } from "./entityService";

/** An overlay reads its base through inclusion rows; conversion (#1388) leaves the Type but clears the base. */
const overlay = { Id: 17, Type: "OrgLIF", BaseDataModelId: 1 };
const converted = { Id: 17, Type: "OrgLIF", BaseDataModelId: null };

describe.each([
    ["entity association", tmplCreateEntityAssociation],
    ["attribute association", tmplCreateEntityAttributeAssociation],
])("the create %s template", (_kind, template) => {
    it("marks an overlay's new association as its extension", () => {
        const params = template(5, overlay);
        expect(params.Extension).toBe(true);
        expect(params.ExtendedByDataModelId).toBe(17);
    });

    it("writes a converted model's new association as its own, not as an ExtendedBy row", () => {
        const params = template(5, converted);
        expect(params.Extension).toBe(false);
        expect(params.ExtendedByDataModelId).toBeUndefined();
    });
});
