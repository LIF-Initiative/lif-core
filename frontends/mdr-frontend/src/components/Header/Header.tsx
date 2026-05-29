import React, { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Badge, Button, DropdownMenu, Flex, Text } from "@radix-ui/themes";
import { PersonIcon, ExitIcon, EnterIcon, LayersIcon } from "@radix-ui/react-icons";
import { useAuth } from "../../context/AuthContext";
import authService from "../../services/authService";
import tenantsService, {
  WORKSPACE_CHANGE_EVENT,
  type WorkspaceItem,
} from "../../services/tenantsService";
import "./Header.css";

const Header: React.FC = () => {
  const navigate = useNavigate();
  const auth = useAuth();

  let user = null;
  let logout = async () => { };

  if (auth) {
    user = auth.user;
    logout = auth.logout;
  } else {
    console.warn("Auth context not available in Header, using fallback");
    logout = async () => {
      await authService.logout();
    };
  }

  // Subscribe to the currently-selected workspace (mirrored in localStorage by
  // tenantsService.select). Re-read on the custom event we dispatch when the
  // selection changes, and on the cross-tab `storage` event so multi-tab users
  // see the same indicator everywhere.
  const [currentWorkspace, setCurrentWorkspace] = useState<WorkspaceItem | null>(
    () => tenantsService.getCurrentWorkspace(),
  );
  useEffect(() => {
    const refresh = () => setCurrentWorkspace(tenantsService.getCurrentWorkspace());
    window.addEventListener(WORKSPACE_CHANGE_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(WORKSPACE_CHANGE_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  const handleLogout = async () => {
    // Clear the mirrored workspace before the auth redirect; otherwise the
    // next user on the same browser would briefly see the previous user's
    // workspace badge before their own selection lands.
    tenantsService.clearCurrentWorkspace();
    await logout();
    // For Cognito, logout() redirects away. For legacy, navigate to login.
    if (!auth?.isCognito) {
      navigate("/login", { replace: true });
    }
  };

  const displayName = user?.name || user?.email || "User";
  const displayDetail = user?.organization;

  return (
    <header className="app-header">
      <div className="header-content">
        <div className="logo-section">
          <div className="logo-icon">
            <a href="/"><img src="/logo.png" alt="LIF MDR Logo" width="32" height="32" /></a>
          </div>
          <a href="/"><h1>LIF MDR</h1></a>
        </div>
        <nav className="main-nav">
          <NavLink
            to="/explore"
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            Explore
          </NavLink>
          <NavLink
            to="/workspaces"
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            Workspaces
          </NavLink>
        </nav>

        {/* User dropdown sits in its natural left-packed position right
            after the nav; the workspace badge below is pulled out of this
            Flex and pushed to the far-right edge of the header so it has
            breathing room (PM ask 2026-05-27: don't crowd the user ID). */}
        <Flex align="center" gap="3">
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              <Button variant="ghost" size="2">
                <PersonIcon />
                <Text size="2">{displayName}</Text>
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content>
              <DropdownMenu.Label>
                <Text size="2" weight="medium">{displayName}</Text>
                {displayDetail && (
                  <>
                    &nbsp;
                    <Text size="1" color="gray" className="block">({displayDetail})</Text>
                  </>
                )}
              </DropdownMenu.Label>
              <DropdownMenu.Separator />
              <DropdownMenu.Item onClick={() => navigate("/workspaces")}>
                <EnterIcon />
                Switch workspace
              </DropdownMenu.Item>
              <DropdownMenu.Separator />
              <DropdownMenu.Item onClick={handleLogout}>
                <ExitIcon />
                Sign out
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </Flex>

        {/* Workspace badge: sibling of the user-area Flex, with auto
            left margin so it pushes to the right edge of header-content
            (which uses justify-content: flex-start + gap: 2rem). The
            gap still applies as a minimum spacer between the dropdown
            and the badge; the auto margin absorbs any remaining slack
            so the badge always lands at the page's right edge.

            Defensive guard on `tenant_schema`: the TypeScript type marks
            it required, but `currentWorkspace` originates from
            localStorage — runtime-untyped — so a corrupted or partially-
            written value could otherwise render the badge with the
            friendly-name line populated and the schema line blank.
            Hiding the entire badge in that case is the safer rendering
            (Adam Hungerford review note 2026-05-27). */}
        {currentWorkspace && currentWorkspace.tenant_schema && (
          <Badge
            color="iris"
            variant="soft"
            size="2"
            title={`Schema: ${currentWorkspace.tenant_schema}`}
            style={{ marginLeft: "auto" }}
          >
            <LayersIcon />
            <Flex direction="column" align="start" gap="0">
              {/* `display_name` (#943) — email for personal tenants, group
                  name for shared. Backend (#947) guarantees this is non-
                  empty (compute_display_name falls through to
                  tenant_schema rather than emit empty). `||` not `??` so
                  a corrupted runtime value still falls back to `group`
                  rather than rendering as a blank label. */}
              <Text size="2" weight="medium">
                {currentWorkspace.display_name || currentWorkspace.group}
              </Text>
              <Text size="1" color="gray" style={{ fontFamily: "monospace" }}>
                {currentWorkspace.tenant_schema}
              </Text>
            </Flex>
          </Badge>
        )}
      </div>
    </header>
  );
};

export default Header;
