import { describe, it, expect } from "vitest";
import jsonata from "jsonata";
import { quoteJsonataSegment } from "./jsonataUtils";

/** Build a path from segments the way ExpressionEditor's suggestions do, then evaluate it. */
const evaluatePath = (input: unknown, ...segs: string[]) =>
    jsonata(segs.map(quoteJsonataSegment).join(".")).evaluate(input);

describe("quoteJsonataSegment", () => {
    it("leaves a plain identifier unquoted", () => {
        expect(quoteJsonataSegment("firstName")).toBe("firstName");
        expect(quoteJsonataSegment("_id2")).toBe("_id2");
    });

    it.each([
        ["first name"],
        ["first-name"],
        ["2ndPlace"],
        ['say "hi"'],
        ["back\\slash"],
        ["tick`name"],
    ])("builds a path that reads the field %j", async (field) => {
        const input = { Person: { [field]: "value" } };
        await expect(evaluatePath(input, "Person", field)).resolves.toBe("value");
    });
});
