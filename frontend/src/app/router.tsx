import { Navigate, type RouteObject, createBrowserRouter } from "react-router-dom";
import ArchitecturePage from "../pages/ArchitecturePage";
import DesignSystemPage from "../pages/DesignSystemPage";
import DiscoveryPage from "../pages/DiscoveryPage";
import DocumentationPage from "../pages/DocumentationPage";
import IaPage from "../pages/IaPage";
import JourneysPage from "../pages/JourneysPage";
import LoginPage from "../pages/LoginPage";
import NotFoundPage from "../pages/NotFoundPage";
import { AnalyticsPage, PerformancePage, SeoPage } from "../pages/OptimizationPage";
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
import { ProtectedRoute, PublicOnlyRoute } from "../features/auth/guards";

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
      { path: "/projects", element: <ProjectsPage /> },
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
          { path: "architecture", element: <ArchitecturePage /> },
          { path: "seo", element: <SeoPage /> },
          { path: "analytics", element: <AnalyticsPage /> },
          { path: "performance", element: <PerformancePage /> },
          { path: "documentation", element: <DocumentationPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: ":section", element: <SectionPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];

export const buildRouter = () => createBrowserRouter(routes);
export const createAppRouter = buildRouter;
