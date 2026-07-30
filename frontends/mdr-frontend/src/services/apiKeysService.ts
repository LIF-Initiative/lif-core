import api from "./api";

// Wire types match the MDR /api-keys responses verbatim (PascalCase), per #1033.
export interface ApiKey {
  Id: number;
  Label: string;
  KeyPrefix: string;
  CreationDate: string | null;
  LastUsedDate: string | null;
  RevokedDate: string | null;
}

// Create returns the raw key exactly once (never again) alongside the metadata.
export interface CreateApiKeyResponse {
  Id: number;
  Label: string;
  KeyPrefix: string;
  CreationDate: string | null;
  Key: string;
}

class ApiKeysService {
  async listApiKeys(): Promise<ApiKey[]> {
    const response = await api.get<ApiKey[]>("/api-keys/");
    return response.data;
  }

  async createApiKey(label: string): Promise<CreateApiKeyResponse> {
    const response = await api.post<CreateApiKeyResponse>("/api-keys/", { Label: label });
    return response.data;
  }

  async revokeApiKey(id: number): Promise<void> {
    await api.delete(`/api-keys/${id}`);
  }
}

export default new ApiKeysService();
