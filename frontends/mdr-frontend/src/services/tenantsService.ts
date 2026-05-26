import api from "./api";

// ---- Wire types matching the MDR API surface (issue #884) ----

export interface WorkspaceItem {
  group: string;
  tenant_schema: string;
  /**
   * Friendly human-readable label (issue #943). For a user's own auto-
   * created personal tenant this is their email; for shared groups
   * (lif-team, etc.) it's the group name. Optional on the wire because
   * the backend rollout may lag the frontend — callers should fall back
   * to `group` when this is missing.
   */
  display_name?: string;
}

interface ListMyWorkspacesResponse {
  workspaces: WorkspaceItem[];
}

export interface SelectWorkspaceResponse {
  group: string;
  tenant_schema: string;
  display_name?: string;
}

export interface CreateInviteResponse {
  token: string;
  group: string;
  /** Unix epoch seconds. */
  expires_at: number;
}

export interface AcceptInviteResponse {
  group: string;
  tenant_schema: string;
  inviter_sub: string;
}

// ---- Service ----

/**
 * Wraps the /tenants/* endpoints from PR #914 + PR #918.
 * The MDR API auth middleware reads/writes the `lif_workspace` cookie
 * on /select; the frontend never sees the cookie value directly.
 */
class TenantsService {
  async listMine(): Promise<WorkspaceItem[]> {
    const response = await api.get<ListMyWorkspacesResponse>("/tenants/mine");
    return response.data.workspaces;
  }

  async select(group: string): Promise<SelectWorkspaceResponse> {
    const response = await api.post<SelectWorkspaceResponse>("/tenants/select", { group });
    return response.data;
  }

  async createInvite(group: string): Promise<CreateInviteResponse> {
    const response = await api.post<CreateInviteResponse>("/tenants/invite", { group });
    return response.data;
  }

  async acceptInvite(token: string): Promise<AcceptInviteResponse> {
    const response = await api.post<AcceptInviteResponse>("/tenants/invite/accept", { token });
    return response.data;
  }
}

export default new TenantsService();
