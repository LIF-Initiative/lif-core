import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

import api from "./api";
import { getActiveGroupIdForPair } from "./transformationsService";

const httpError = (status: number) => Object.assign(new Error(`HTTP ${status}`), { response: { status } });

describe("getActiveGroupIdForPair", () => {
    beforeEach(() => {
        vi.mocked(api.get).mockReset();
    });

    it("returns the live group's Id", async () => {
        vi.mocked(api.get).mockResolvedValue({ data: { TransformationGroupId: 54, GroupVersion: "3.0" } });
        expect(await getActiveGroupIdForPair(26, 17)).toBe(54);
        expect(vi.mocked(api.get).mock.calls[0][0]).toContain(
            "/transformation_groups/active_transformations_for_data_models/?source_data_model_id=26&target_data_model_id=17"
        );
    });

    it("returns null when the pair has no live version (404)", async () => {
        vi.mocked(api.get).mockRejectedValue(httpError(404));
        expect(await getActiveGroupIdForPair(4, 1)).toBeNull();
    });

    it("rethrows anything else, such as a tie between active versions (409)", async () => {
        vi.mocked(api.get).mockRejectedValue(httpError(409));
        await expect(getActiveGroupIdForPair(26, 17)).rejects.toThrow("HTTP 409");
    });
});
