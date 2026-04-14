import {
  createBrowserRouter,
  RouteObject,
  // NonIndexRouteObject,
} from "react-router-dom";

import Home from "../pages/Home";
import Login from "../pages/Login";
import AuthCallback from "../pages/AuthCallback";
import AuthGuard from "../components/AuthGuard";
import LifModel from "./Explore/lif-model";
import DataExtensions from "./Explore/data-extensions";
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
    path: "/",
    element: <AuthGuard><Home /></AuthGuard>,
    handle: { name: "Dashboard" },
    children: [
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
