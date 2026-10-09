import {
  createBrowserRouter,
  RouteObject,
  // NonIndexRouteObject,
} from "react-router-dom";

import Home from "./Home";
import Login from "./Login";
import AuthCallback from "./AuthCallback";
import Workspaces from "./Workspaces";
import ApiKeys from "./ApiKeys";
import ExportPlayground from "./ExportPlayground";
import InviteAccept from "./InviteAccept";
import AuthGuard from "../components/AuthGuard/AuthGuard";
import LifModel from "./Explore/LifModel";
import DataExtensions from "./Explore/DataExtensions";
import ExploreSearch from "./Explore/ExploreSearch";
import MappingsView from "./Explore/Mappings/MappingsView";
import TabLayout from "./Explore/TabLayout";
import DataModelsTab from "./Explore/DataModelsTab";

const routes: RouteObject[] = [
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/auth/callback",
    element: <AuthCallback />,
  },
  {
    // Standalone, focused-card layout (no header/footer chrome) — feels like a
    // transactional step, similar to AuthCallback. Wrapped in AuthGuard so an
    // unauthenticated click bounces through login first, then returns here.
    path: "/invite/accept",
    element: <AuthGuard><InviteAccept /></AuthGuard>,
  },
  {
    path: "/",
    element: <AuthGuard><Home /></AuthGuard>,
    handle: { name: "Dashboard" },
    children: [
      {
        // Workspace landing page. Lives inside the / parent so it renders
        // through Layout's <Outlet/> with the standard header + footer chrome.
        path: "workspaces",
        element: <Workspaces />,
        handle: { name: "Workspaces" },
      },
      {
        // Per-user developer API keys for the Learner Data Export API (#1035).
        path: "api-keys",
        element: <ApiKeys />,
        handle: { name: "API Keys" },
      },
      {
        // Interactive LDE /exports playground: pick a test learner + format (#1036).
        path: "export-playground",
        element: <ExportPlayground />,
        handle: { name: "Export Playground" },
      },
      {
        path: "explore",
        element: <TabLayout />,
        handle: { name: "Explore" },
        children: [
          {
            index: true,
            element: <DataModelsTab />,
          },
          {
            path: "lif-model",
            element: <LifModel />,
            handle: { name: "The LIF Model" },
            children: [
              {
                path: ":modelId",
                element: <LifModel />,
                handle: { name: "The LIF Model" },
                children: [
                  {
                    path: "entities/:entityId",
                    element: <LifModel />,
                    handle: { name: "The LIF Model" },
                  },
                  {
                    path: "value-sets/:valueSetId",
                    element: <LifModel />,
                    handle: { name: "The LIF Model" },
                    children: [
                      {
                        path: "values/:valueId",
                        element: <LifModel />,
                        handle: { name: "The LIF Model" },
                      },
                      {
                        path: "attributes/:attributeId",
                        element: <LifModel />,
                        handle: { name: "The LIF Model" },
                      },
                    ],
                  },
                ],
              },
            ],
          },
          {
            path: "data-models",
            element: <DataModelsTab />,
            handle: { name: "Data Models" },
            children: [
              {
                path: ":modelId",
                element: <DataModelsTab />,
                handle: { name: "Data Models" },
                children: [
                  {
                    path: "only",
                    element: <DataModelsTab />,
                    handle: { name: "Data Models" },
                  },
                  {
                    path: "all",
                    element: <DataModelsTab />,
                    handle: { name: "Data Models" },
                  },
                  {
                    path: "public",
                    element: <DataModelsTab />,
                    handle: { name: "Data Models" },
                  },
                  {
                    path: "extensions",
                    element: <DataModelsTab />,
                    handle: { name: "Data Models" },
                  },
                  {
                    path: "partner",
                    element: <DataModelsTab />,
                    handle: { name: "Data Models" },
                  },
                  {
                    path: "entities/:entityId",
                    element: <DataModelsTab />,
                    handle: { name: "Data Models" },
                  },
                  {
                    path: "value-sets/:valueSetId",
                    element: <DataModelsTab />,
                    handle: { name: "Data Models" },
                    children: [
                    ],
                  },
                  {
                    path: "values/:valueId",
                    element: <DataModelsTab />,
                    handle: { name: "Data Models" },
                  },
                  {
                    path: "attributes/:attributeId",
                    element: <DataModelsTab />,
                    handle: { name: "Data Models" },
                  },
                ],
              },
            ],
          },
          {
            path: "data-extensions",
            element: <DataExtensions />,
            handle: { name: "Extensions" },
            children: [
              {
                path: ":modelId",
                element: <DataExtensions />,
                handle: { name: "Extensions" },
                children: [
                  {
                    path: "entities/:entityId",
                    element: <DataExtensions />,
                    handle: { name: "Extensions" },
                  },
                  {
                    path: "value-sets/:valueSetId",
                    element: <DataExtensions />,
                    handle: { name: "Extensions" },
                    children: [
                      {
                        path: "values/:valueId",
                        element: <DataExtensions />,
                        handle: { name: "Extensions" },
                      },
                      {
                        path: "attributes/:attributeId",
                        element: <DataExtensions />,
                        handle: { name: "Extensions" },
                      },
                    ],
                  },
                ],
              },
            ],
          },
          {
            path: "data-mappings",
            element: <MappingsView />,
            handle: { name: "Mappings" },
          },
          {
            path: "data-mappings/:groupId",
            element: <MappingsView />,
          },
          {
            path: "search",
            element: <ExploreSearch />,
          },
        ],
      },
      // {
      //   path: "learn",
      //   element: <LearnLayout />,
      //   handle: { name: "Learn" },
      //   children: [
      //     {
      //       path: "user-guide",
      //       element: <h1>User Guide</h1>,
      //       handle: { name: "User Guide" },
      //     },
      //   ],
      // },
      // {
      //   path: "analyze",
      //   element: <AnalyzeLayout />,
      //   handle: { name: "Analyze" },
      //   children: [
      //     {
      //       path: "metrics",
      //       element: <h1>Usage Metrics</h1>,
      //       handle: { name: "Metrics" },
      //     },
      //   ],
      // },
    ],
  },
];

const router = createBrowserRouter(routes);
// const router = createBrowserRouter(routes);

export default router;
