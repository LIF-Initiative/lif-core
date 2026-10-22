import React, { useEffect } from "react";
import { RouteObject, useLocation, useMatches } from "react-router-dom";
import { useMdrContext } from "@/context/MdrContext";
import router from "@/pages/Routes";

// Helper function to find route config by pathname
const findRouteConfig = (pathname: string): RouteObject | null => {
  // Remove leading slash and get the first segment
  const segment = pathname.replace(/^\//, "").split("/")[0];

  // Get the root route's children (top-level routes)
  const rootRoute = router.routes[0] as RouteObject;
  const rootChildren = rootRoute?.children || [];

  // Find matching route
  return rootChildren.find((route) => route.path === segment) || null;
};

export const RouterWrapper: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const location = useLocation();
  const matches = useMatches();
  const { setRouteInfo } = useMdrContext();

  useEffect(() => {
    const routeMatches = matches.filter((match) => match.handle);

    // Get current route match
    const current = routeMatches[routeMatches.length - 1];

    // Find the top-level section route (explore, learn, analyze)
    const topLevelRoute = findRouteConfig(location.pathname);

    setRouteInfo({
      currentRoute: current
        ? {
            ...current,
            path: current.pathname,
            handle: current.handle as { name: string; [key: string]: any },
          }
        : null,
      parentRoute: topLevelRoute
        ? {
            ...topLevelRoute,
            path: `${topLevelRoute.path}`,
            handle: topLevelRoute.handle as {
              name: string;
              [key: string]: any;
            },
          }
        : null,
      breadcrumbs: routeMatches.map((match) => ({
        ...match,
        path: match.pathname,
        handle: match.handle as { name: string; [key: string]: any },
      })),
    });
  }, [location, matches, setRouteInfo]);

  return <>{children}</>;
};
