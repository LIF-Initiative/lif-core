import api from "./api";

// ---- Wire types matching the MDR API surface (issue #884) ----

export interface WorkspaceItem {
  group: string;
  tenant_schema: string;
  /**
   * Friendly human-readable label (issue #943). For a user's own auto-
   * created personal tenant this is their email; for shared groups
   * (lif-team, etc.) it's the group name. The backend guarantees this
   * field is always present and non-empty — `compute_display_name`
   * falls through to `tenant_schema` rather than ever returning an
   * empty string. Consumers that still want to be defensive about
   * runtime corruption (e.g. localStorage cookie mirror) should use
   * `display_name || group` rather than `display_name ?? group` so an
   * empty-string edge case doesn't render as a blank label.
   */
  display_name: string;
}

interface ListMyWorkspacesResponse {
  workspaces: WorkspaceItem[];
}

export interface SelectWorkspaceResponse {
  group: string;
  tenant_schema: string;
  display_name: string;
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

// ---- Currently-selected workspace (client-side mirror) ----
//
// The backend writes the actual selection into the HttpOnly `lif_workspace`
// cookie, which the frontend can't read. We mirror the selection into
// localStorage so the header can show "you are operating against <X>" without
// a round-trip to the backend.
//
// Trade-off accepted for v1: localStorage is per-browser. A user on a fresh
// browser whose cookie is still valid (server-side) will see the indicator
// as empty until their next /tenants/select call. Issue #936 tracks the
// proper backend-driven `GET /tenants/current` follow-up.

const WORKSPACE_STORAGE_KEY = "lif:currentWorkspace";
const WORKSPACE_CHANGE_EVENT = "lif:workspace-changed";

function readCurrentWorkspace(): WorkspaceItem | null {
  try {
    const raw = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as WorkspaceItem) : null;
  } catch {
    return null;
  }
}

function writeCurrentWorkspace(workspace: WorkspaceItem | null): void {
  try {
    if (workspace) {
      window.localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(workspace));
    } else {
      window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
    }
    window.dispatchEvent(new CustomEvent(WORKSPACE_CHANGE_EVENT));
  } catch {
    // localStorage can throw in private-mode Safari etc. Indicator is
    // best-effort; failing silently is preferable to blocking the select.
  }
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
    // Mirror into localStorage so the header indicator reflects the change.
    writeCurrentWorkspace(response.data);
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

  getCurrentWorkspace(): WorkspaceItem | null {
    return readCurrentWorkspace();
  }

  clearCurrentWorkspace(): void {
    writeCurrentWorkspace(null);
  }
}

export { WORKSPACE_CHANGE_EVENT };
export default new TenantsService();
