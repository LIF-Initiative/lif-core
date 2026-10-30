import api from "./api";
import { errorToString } from "../utils/errorUtils";

const apiBaseUrl = import.meta.env.VITE_API_URL;

/** One reason the MDR API refused a portable file: its code, the element it concerns, and why. */
export interface Refusal {
    code: string;
    element: string;
    reason: string;
}

/** Why a portable import or export failed: every refusal, or one message. */
export type PortableFailure =
    | { kind: "refused"; status: number; refusals: Refusal[] }
    | { kind: "message"; message: string };

/** The part of an axios error these functions read. */
type HttpError = { response?: { status: number; data?: unknown } };

const isRefusal = (value: unknown): value is Refusal =>
    !!value && typeof value === "object" && "code" in value && "element" in value && "reason" in value;

/** Describe an error from a portable import or export for display. */
export const describePortableFailure = (error: unknown): PortableFailure => {
    const response = (error as HttpError | undefined)?.response;
    const detail = (response?.data as { detail?: unknown } | undefined)?.detail;
    if (response && Array.isArray(detail) && detail.length > 0 && detail.every(isRefusal)) {
        return { kind: "refused", status: response.status, refusals: detail };
    }
    // A string detail: a missing Id (404) or a concurrent import of the same content (409).
    if (typeof detail === "string") return { kind: "message", message: detail };
    return { kind: "message", message: errorToString(error) };
};

/** A blob response's error body is a Blob too, so read it back as JSON for describePortableFailure. */
const readErrorBody = async (error: unknown): Promise<never> => {
    const response = (error as HttpError | undefined)?.response;
    if (response?.data instanceof Blob) {
        try {
            response.data = JSON.parse(await response.data.text());
        } catch {
            // Not JSON, such as a gateway error page; describePortableFailure falls back to the status.
        }
    }
    throw error;
};

/** The file exactly as the API wrote it, so its canonical bytes are kept. */
const exportFile = async (path: string): Promise<Blob> => {
    try {
        const result = await api.get<Blob>(`${apiBaseUrl}${path}`, { responseType: "blob" });
        return result.data;
    } catch (error) {
        return readErrorBody(error);
    }
};

/** Send the file's bytes unchanged: the API reads the raw body, not re-encoded JSON. */
const importFile = async <T>(path: string, file: File): Promise<T> => {
    const result = await api.post<T>(`${apiBaseUrl}${path}`, file, {
        headers: { "Content-Type": "application/json" },
    });
    return result.data;
};

export const exportPortableModel = (dataModelId: number) => exportFile(`/portable/models/${dataModelId}`);

export const exportPortableMappingGroup = (groupId: number) => exportFile(`/portable/mapping_groups/${groupId}`);

export const exportPortableCrosswalk = (sourceValueSetId: number, targetValueSetId: number) =>
    exportFile(
        `/portable/crosswalks?source_value_set_id=${sourceValueSetId}&target_value_set_id=${targetValueSetId}`
    );

/** Import a model file as a new model, and return its Id. */
export const importPortableModel = (file: File) => importFile<{ Id: number }>("/portable/models", file);

/** Import a mapping-group file as a new, inactive group, and return its Id. */
export const importPortableMappingGroup = (file: File) => importFile<{ Id: number }>("/portable/mapping_groups", file);

/** Import a crosswalk file, and return how many value mappings it created. */
export const importPortableCrosswalk = (file: File) => importFile<{ Created: number }>("/portable/crosswalks", file);
