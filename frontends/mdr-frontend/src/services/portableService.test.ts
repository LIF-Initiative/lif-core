import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

import api from "./api";
import {
    describePortableFailure,
    exportPortableCrosswalk,
    exportPortableModel,
    importPortableCrosswalk,
    importPortableModel,
} from "./portableService";

const refusals = [
    { code: "MODEL_EXISTS", element: "Details", reason: "model 7 already has this identity" },
    { code: "DUPLICATE_KEY", element: "Entities[Student]", reason: "2 entities share this key" },
];

const httpError = (status: number, data: unknown) =>
    Object.assign(new Error(`HTTP ${status}`), { response: { status, data } });

describe("portable imports", () => {
    beforeEach(() => {
        vi.mocked(api.post).mockReset();
    });

    it("sends the file itself, so the API reads its bytes as written", async () => {
        // A BOM and a repeated key: JSON.parse and JSON.stringify would drop both.
        const file = new File(['﻿{"Format": {}, "Format": {}}'], "model.json", { type: "application/json" });
        vi.mocked(api.post).mockResolvedValue({ data: { Id: 42 } });

        expect(await importPortableModel(file)).toEqual({ Id: 42 });
        const [url, body, config] = vi.mocked(api.post).mock.calls[0];
        expect(url).toMatch(/\/portable\/models$/);
        expect(body).toBe(file);
        expect(config?.headers).toEqual({ "Content-Type": "application/json" });
    });

    it("returns how many value mappings a crosswalk created", async () => {
        vi.mocked(api.post).mockResolvedValue({ data: { Created: 3 } });
        expect(await importPortableCrosswalk(new File(["{}"], "crosswalk.json"))).toEqual({ Created: 3 });
        expect(vi.mocked(api.post).mock.calls[0][0]).toMatch(/\/portable\/crosswalks$/);
    });
});

describe("portable exports", () => {
    beforeEach(() => {
        vi.mocked(api.get).mockReset();
    });

    it("returns the response as a blob, not re-encoded JSON", async () => {
        const blob = new Blob(['{\n  "Format": {}\n}\n'], { type: "application/json" });
        vi.mocked(api.get).mockResolvedValue({ data: blob });

        expect(await exportPortableModel(5)).toBe(blob);
        const [url, config] = vi.mocked(api.get).mock.calls[0];
        expect(url).toMatch(/\/portable\/models\/5$/);
        expect(config).toEqual({ responseType: "blob" });
    });

    it("asks for a crosswalk by its two value sets", async () => {
        vi.mocked(api.get).mockResolvedValue({ data: new Blob(["{}"]) });
        await exportPortableCrosswalk(11, 12);
        expect(vi.mocked(api.get).mock.calls[0][0]).toMatch(
            /\/portable\/crosswalks\?source_value_set_id=11&target_value_set_id=12$/
        );
    });

    it("reads a refusal list out of a blob error body", async () => {
        const body = new Blob([JSON.stringify({ detail: [refusals[1]] })], { type: "application/json" });
        vi.mocked(api.get).mockRejectedValue(httpError(422, body));

        const error = await exportPortableModel(1).catch((caught) => caught);

        expect(describePortableFailure(error)).toEqual({ kind: "refused", status: 422, refusals: [refusals[1]] });
    });

    it("leaves an error body that isn't JSON for the fallback message", async () => {
        vi.mocked(api.get).mockRejectedValue(httpError(502, new Blob(["<html>Bad Gateway</html>"])));

        const error = await exportPortableModel(1).catch((caught) => caught);

        expect(describePortableFailure(error).kind).toBe("message");
    });
});

describe("describePortableFailure", () => {
    it("lists every refusal, with the status", () => {
        expect(describePortableFailure(httpError(422, { detail: refusals }))).toEqual({
            kind: "refused",
            status: 422,
            refusals,
        });
    });

    it("gives a string detail as the message, such as a concurrent import's 409", () => {
        const detail = "Another import of the same content finished first; nothing was written.";
        expect(describePortableFailure(httpError(409, { detail }))).toEqual({ kind: "message", message: detail });
    });

    it.each([
        ["FastAPI's own validation errors", httpError(422, { detail: [{ loc: ["query"], msg: "field required" }] })],
        ["a network error with no response", new Error("Network Error")],
    ])("falls back to a message for %s", (_case, error) => {
        expect(describePortableFailure(error).kind).toBe("message");
    });
});
