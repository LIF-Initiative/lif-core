import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

import api from "./api";
import { getLiveVersionForPair } from "./transformationsService";

const httpError = (status: number) => Object.assign(new Error(`HTTP ${status}`), { response: { status } });

describe("getLiveVersionForPair", () => {
    beforeEach(() => {
        vi.mocked(api.get).mockReset();
        vi.spyOn(console, "error").mockImplementation(() => {});
    });

    it("returns the live group's Id", async () => {
        vi.mocked(api.get).mockResolvedValue({ data: { TransformationGroupId: 54, GroupVersion: "3.0" } });
        expect(await getLiveVersionForPair(26, 17)).toEqual({ status: "live", groupId: 54 });
        expect(vi.mocked(api.get).mock.calls[0][0]).toContain(
            "/transformation_groups/active_transformations_for_data_models/?source_data_model_id=26&target_data_model_id=17"
        );
    });

    it("reports no live version for a 404", async () => {
        vi.mocked(api.get).mockRejectedValue(httpError(404));
        expect(await getLiveVersionForPair(4, 1)).toEqual({ status: "none" });
    });

    it("reports a tie for a 409, not 'no live version'", async () => {
        vi.mocked(api.get).mockRejectedValue(httpError(409));
        expect(await getLiveVersionForPair(26, 17)).toEqual({ status: "tie" });
    });

    it.each([
        ["a 500", httpError(500)],
        ["a network error with no response", new Error("Network Error")],
    ])("reports an unknown live version for %s, not 'no live version'", async (_case, error) => {
        vi.mocked(api.get).mockRejectedValue(error);
        expect(await getLiveVersionForPair(26, 17)).toEqual({ status: "error" });
    });
});
