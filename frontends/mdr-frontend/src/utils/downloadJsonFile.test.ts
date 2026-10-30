import { describe, it, expect } from "vitest";
import { toDownloadFilename } from "./downloadJsonFile";

describe("toDownloadFilename", () => {
    const suffix = "_v1.0.lif-mdr-mapping-group.json";

    it("keeps the suffix and shortens a long name to fit 255 characters", () => {
        const filename = toDownloadFilename("x".repeat(300), suffix);
        expect(filename).toHaveLength(255);
        expect(filename.endsWith(suffix)).toBe(true);
    });

    it("removes characters no operating system allows, from the name and the suffix", () => {
        expect(toDownloadFilename('Kona/Bozeman: "draft" <v2>?*|\\', "_1.0/beta.lif-mdr-model.json")).toBe(
            "KonaBozeman_draft_v2_1.0beta.lif-mdr-model.json"
        );
    });

    it("turns whitespace into underscores and drops leading and trailing dots", () => {
        expect(toDownloadFilename("  ..Hawaii\tKona  University..  ", suffix)).toBe(
            "Hawaii_Kona_University_v1.0.lif-mdr-mapping-group.json"
        );
    });

    it("cannot write outside the download folder", () => {
        expect(toDownloadFilename("../../etc/passwd", ".json")).toBe("etcpasswd.json");
    });

    it("prefixes a reserved Windows device name", () => {
        expect(toDownloadFilename("CON", ".json")).toBe("_CON.json");
    });

    it.each([
        ["CON.v2", "_1.0.lif-mdr-model.json", "_CON.v2_1.0.lif-mdr-model.json"],
        ["nul.backup", ".json", "_nul.backup.json"],
        ["Lpt1.2026", "_v1.0.lif-mdr-mapping-group.json", "_Lpt1.2026_v1.0.lif-mdr-mapping-group.json"],
    ])("prefixes a reserved device name before the first dot, in any case: %s", (name, suffix, expected) => {
        expect(toDownloadFilename(name, suffix)).toBe(expected);
    });

    it("leaves a name that only starts with a device name alone", () => {
        expect(toDownloadFilename("CONSOLE.v2", ".json")).toBe("CONSOLE.v2.json");
        expect(toDownloadFilename("Comics.2026", ".json")).toBe("Comics.2026.json");
    });

    it("falls back to 'data' for a name with nothing usable in it", () => {
        expect(toDownloadFilename("///", suffix)).toBe("data_v1.0.lif-mdr-mapping-group.json");
    });

    it("keeps Unicode", () => {
        expect(toDownloadFilename("Línea Ñandú 📚", ".json")).toBe("Línea_Ñandú_📚.json");
    });
});
