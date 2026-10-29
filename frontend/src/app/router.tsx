import { lazy, Suspense } from "react";
import { Navigate, type RouteObject, createBrowserRouter } from "react-router-dom";

import { LoadingState } from "../components/feedback/States";
import AppShell from "../components/layout/AppShell";
import { ProtectedRoute, PublicOnlyRoute } from "../features/auth/guards";
import DesignSystemPage from "../pages/DesignSystemPage";
import DiscoveryPage from "../pages/DiscoveryPage";
import IaPage from "../pages/IaPage";
import JourneysPage from "../pages/JourneysPage";
import LoginPage from "../pages/LoginPage";
import NotFoundPage from "../pages/NotFoundPage";
import ProjectOverviewPage from "../pages/ProjectOverviewPage";
import PersonasPage from "../pages/PersonasPage";
import PrdPage from "../pages/PrdPage";
import ProjectLayout from "../pages/ProjectLayout";
import ProjectsPage from "../pages/ProjectsPage";
import PrototypePage from "../pages/PrototypePage";
import RegisterPage from "../pages/RegisterPage";
import ResearchPage from "../pages/ResearchPage";
import SectionPage from "../pages/SectionPage";
import SettingsPage from "../pages/SettingsPage";
import StrategyPage from "../pages/StrategyPage";
import UxReviewPage from "../pages/UxReviewPage";
import WireframesPage from "../pages/WireframesPage";

const ArchitecturePage = lazy(() => import("../pages/ArchitecturePage"));
const DocumentationPage = lazy(() => import("../pages/DocumentationPage"));
const SeoPage = lazy(() =>
  import("../pages/OptimizationPage").then((module) => ({ default: module.SeoPage })),
);
const AnalyticsPage = lazy(() =>
  import("../pages/OptimizationPage").then((module) => ({ default: module.AnalyticsPage })),
);
const PerformancePage = lazy(() =>
  import("../pages/OptimizationPage").then((module) => ({ default: module.PerformancePage })),
);

export const routes: RouteObject[] = [
  { path: "/", element: <Navigate to="/projects" replace /> },
  {
    element: <PublicOnlyRoute />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/register", element: <RegisterPage /> },
    ],
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/projects", element: <ProjectsPage /> },
          { path: "/settings", element: <SettingsPage /> },
          {
            path: "/projects/:projectId",
            element: <ProjectLayout />,
            children: [
              { index: true, element: <Navigate to="overview" replace /> },
              { path: "overview", element: <ProjectOverviewPage /> },
              { path: "discovery", element: <DiscoveryPage /> },
              { path: "research", element: <ResearchPage /> },
              { path: "strategy", element: <StrategyPage /> },
              { path: "prd", element: <PrdPage /> },
              { path: "personas", element: <PersonasPage /> },
              { path: "journeys", element: <JourneysPage /> },
              { path: "ia", element: <IaPage /> },
              { path: "wireframes", element: <WireframesPage /> },
              { path: "ux-review", element: <UxReviewPage /> },
              { path: "design-system", element: <DesignSystemPage /> },
              { path: "prototype", element: <PrototypePage /> },
              {
                path: "architecture",
                element: (
                  <Suspense fallback={<LoadingState label="Loading Architecture..." />}>
                    <ArchitecturePage />
                  </Suspense>
                ),
              },
              {
                path: "seo",
                element: (
                  <Suspense fallback={<LoadingState label="Loading SEO..." />}>
                    <SeoPage />
                  </Suspense>
                ),
              },
              {
                path: "analytics",
                element: (
                  <Suspense fallback={<LoadingState label="Loading Analytics..." />}>
                    <AnalyticsPage />
                  </Suspense>
                ),
              },
              {
                path: "performance",
                element: (
                  <Suspense fallback={<LoadingState label="Loading Performance..." />}>
                    <PerformancePage />
                  </Suspense>
                ),
              },
              {
                path: "documentation",
                element: (
                  <Suspense fallback={<LoadingState label="Loading Documentation..." />}>
                    <DocumentationPage />
                  </Suspense>
                ),
              },
              { path: "settings", element: <SettingsPage /> },
              { path: ":section", element: <SectionPage /> },
            ],
          },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];

export const buildRouter = () => createBrowserRouter(routes);
export const createAppRouter = buildRouter;
