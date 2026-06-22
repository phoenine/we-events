import type { ReactNode } from "react";
import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { Spin } from "antd";
import AppLayout from "@/components/layout/AppLayout";
import AdminOnly from "@/components/layout/AdminOnly";
import ProtectedRoute from "@/components/layout/ProtectedRoute";
import LoginPage from "@/pages/login/LoginPage";

const ArticlesPage = lazy(() => import("@/pages/articles/ArticlesPage"));
const WechatAccountsPage = lazy(
  () => import("@/pages/wechat-accounts/WechatAccountsPage")
);
const AddWechatAccountPage = lazy(
  () => import("@/pages/wechat-accounts/AddWechatAccountPage")
);
const WechatAccountGroupsPage = lazy(
  () => import("@/pages/wechat-account-groups/WechatAccountGroupsPage")
);
const ActivitiesPage = lazy(() => import("@/pages/activities/ActivitiesPage"));
const ConfigsPage = lazy(() => import("@/pages/configs/ConfigsPage"));
const SysPage = lazy(() => import("@/pages/sys/SysPage"));
const ProfilePage = lazy(() => import("@/pages/user/ProfilePage"));
const ChangePasswordPage = lazy(
  () => import("@/pages/user/ChangePasswordPage")
);

function LazyPage({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div style={{ display: "grid", minHeight: 240, placeItems: "center" }}>
          <Spin />
        </div>
      }
    >
      {children}
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <AppLayout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Navigate to="/activities" replace /> },
      { path: "articles", element: <LazyPage><ArticlesPage /></LazyPage> },
      { path: "wechat-accounts", element: <LazyPage><WechatAccountsPage /></LazyPage> },
      { path: "wechat-accounts/add", element: <LazyPage><AddWechatAccountPage /></LazyPage> },
      { path: "wechat-account-groups", element: <LazyPage><WechatAccountGroupsPage /></LazyPage> },
      { path: "activities", element: <LazyPage><ActivitiesPage /></LazyPage> },
      {
        path: "configs",
        element: (
          <AdminOnly>
            <LazyPage><ConfigsPage /></LazyPage>
          </AdminOnly>
        ),
      },
      {
        path: "sys",
        element: (
          <AdminOnly>
            <LazyPage><SysPage /></LazyPage>
          </AdminOnly>
        ),
      },
      { path: "profile", element: <LazyPage><ProfilePage /></LazyPage> },
      { path: "change-password", element: <LazyPage><ChangePasswordPage /></LazyPage> },
    ],
  },
]);
