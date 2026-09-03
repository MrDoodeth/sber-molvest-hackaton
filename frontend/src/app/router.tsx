import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import RoleGuard from "./guards/RoleGuard";
import RootLayout from "./layouts/RootLayout";
import { PageLoader } from "../shared/ui";

const LoginPage = lazy(() => import("../features/auth/LoginPage"));
const UserLayout = lazy(() => import("./layouts/UserLayout"));
const OperatorLayout = lazy(() => import("./layouts/OperatorLayout"));
const AdminLayout = lazy(() => import("./layouts/AdminLayout"));
const UserHomePage = lazy(() => import("../features/user-chat/UserHomePage"));
const NewUserDialogPage = lazy(() => import("../features/user-chat/NewUserDialogPage"));
const UserDialogPage = lazy(() => import("../features/user-chat/UserDialogPage"));
const OperatorWorkspace = lazy(() => import("../features/operator/OperatorWorkspace"));
const AdminDialogsPage = lazy(() => import("../features/admin-dialogs/AdminDialogsPage"));
const AdminDialogDetailPage = lazy(() => import("../features/admin-dialogs/AdminDialogDetailPage"));
const KnowledgePage = lazy(() => import("../features/admin-knowledge/KnowledgePage"));
const PromptsPage = lazy(() => import("../features/admin-prompts/PromptsPage"));
const SettingsPage = lazy(() => import("../features/admin-settings/SettingsPage"));
const MonitoringPage = lazy(() => import("../features/admin-monitoring/MonitoringPage"));

function Loading() {
  return <PageLoader label="Открываем раздел" />;
}

function suspended(element: React.ReactNode) {
  return <Suspense fallback={<Loading />}>{element}</Suspense>;
}

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { index: true, element: suspended(<LoginPage />) },
      {
        path: "user",
        element: <RoleGuard allow="user">{suspended(<UserLayout />)}</RoleGuard>,
        children: [
          { index: true, element: suspended(<UserHomePage />) },
          { path: "new", element: suspended(<NewUserDialogPage />) },
          { path: "dialogs/:dialogId", element: suspended(<UserDialogPage />) },
        ],
      },
      {
        path: "operator",
        element: <RoleGuard allow="operator">{suspended(<OperatorLayout />)}</RoleGuard>,
        children: [
          { index: true, element: suspended(<OperatorWorkspace />) },
          { path: "dialogs/:dialogId", element: suspended(<OperatorWorkspace />) },
        ],
      },
      {
        path: "admin",
        element: <RoleGuard allow="admin">{suspended(<AdminLayout />)}</RoleGuard>,
        children: [
          { index: true, element: <Navigate to="dialogs" replace /> },
          { path: "dialogs", element: suspended(<AdminDialogsPage />) },
          { path: "dialogs/:dialogId", element: suspended(<AdminDialogDetailPage />) },
          { path: "knowledge", element: suspended(<KnowledgePage />) },
          { path: "prompts", element: suspended(<PromptsPage />) },
          { path: "settings", element: suspended(<SettingsPage />) },
          { path: "monitoring", element: suspended(<MonitoringPage />) },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
