import { createBrowserRouter, Navigate } from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";
import AdminOnly from "@/components/layout/AdminOnly";
import ProtectedRoute from "@/components/layout/ProtectedRoute";
import LoginPage from "@/pages/login/LoginPage";
import ArticlesPage from "@/pages/articles/ArticlesPage";
import WechatAccountsPage from "@/pages/wechat-accounts/WechatAccountsPage";
import AddWechatAccountPage from "@/pages/wechat-accounts/AddWechatAccountPage";
import WechatAccountGroupsPage from "@/pages/wechat-account-groups/WechatAccountGroupsPage";
import ActivitiesPage from "@/pages/activities/ActivitiesPage";
import ConfigsPage from "@/pages/configs/ConfigsPage";
import SysPage from "@/pages/sys/SysPage";
import ProfilePage from "@/pages/user/ProfilePage";
import ChangePasswordPage from "@/pages/user/ChangePasswordPage";

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
      { path: "articles", element: <ArticlesPage /> },
      { path: "wechat-accounts", element: <WechatAccountsPage /> },
      { path: "wechat-accounts/add", element: <AddWechatAccountPage /> },
      { path: "wechat-account-groups", element: <WechatAccountGroupsPage /> },
      { path: "activities", element: <ActivitiesPage /> },
      { path: "configs", element: <ConfigsPage /> },
      {
        path: "sys",
        element: (
          <AdminOnly>
            <SysPage />
          </AdminOnly>
        ),
      },
      { path: "profile", element: <ProfilePage /> },
      { path: "change-password", element: <ChangePasswordPage /> },
    ],
  },
]);
