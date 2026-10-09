import React, { useEffect } from "react";
import { Tabs, Box } from "@radix-ui/themes";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import "./TabLayout.css";

const TabLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  // Redirect to data-models tab if we're at the base route
  useEffect(() => {
    if (location.pathname === "/explore" || location.pathname === "/explore/") {
      navigate("/explore/data-models", { replace: true });
    }
  }, [location.pathname, navigate]);

  // Determine the current tab based on the URL
  const getCurrentTab = () => {
    if (location.pathname.includes("/lif-model")) {
      return "lif-model";
    } else if (location.pathname.includes("/data-models")) {
      return "data-models";
    } else if (location.pathname.includes("/data-extensions")) {
      return "data-extensions";
    } else if (location.pathname.includes("/data-mappings")) {
      return "data-mappings";
    }
    return "data-models"; // Default to data-models
  };

  const handleTabChange = (value: string) => {
    if (value === "lif-model") {
      navigate("/explore/lif-model");
    } else if (value === "data-models") {
      navigate("/explore/data-models");
    } else if (value === "data-extensions") {
      navigate("/explore/data-extensions");
    } else if (value === "data-mappings") {
      navigate("/explore/data-mappings");
    }
  };

  return (
    <Box className="tab-layout" style={{ height: "100%" }}>
      <Tabs.Root
        value={getCurrentTab()}
        onValueChange={handleTabChange}
        orientation="horizontal"
        style={{ height: "100%", display: "flex", flexDirection: "column" }}
      >
        <Tabs.List className="tab-list"style={{  }}>
          {/* Hidden tabs - uncomment to re-enable */}
          {/* <Tabs.Trigger value="lif-model">The LIF Model</Tabs.Trigger> */}
          <Tabs.Trigger value="data-models">Data Models</Tabs.Trigger>
          {/* <Tabs.Trigger value="data-extensions">Extensions</Tabs.Trigger> */}
          <Tabs.Trigger value="data-mappings">Mappings</Tabs.Trigger>
        </Tabs.List>

        <Box className="tab-content" style={{ flex: 1, overflow: "auto" }}>
          <Outlet />
        </Box>
      </Tabs.Root>
    </Box>
  );
};

export default TabLayout;
