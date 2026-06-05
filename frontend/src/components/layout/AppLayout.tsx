import {
  AppstoreOutlined,
  CalendarOutlined,
  FileTextOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { App, Avatar, Button, Dropdown, Layout, Menu, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { MenuProps } from "antd";
import { logout as logoutApi } from "@/api/auth";
import { getCurrentUser } from "@/api/user";
import { useAuthStore } from "@/store/authStore";

const { Sider, Header, Content } = Layout;

const baseMenuItems: MenuProps["items"] = [
  { key: "/activities", icon: <CalendarOutlined />, label: <Link to="/activities">活动</Link> },
  { key: "/articles", icon: <FileTextOutlined />, label: <Link to="/articles">文章</Link> },
  {
    key: "/wechat-accounts",
    icon: <TeamOutlined />,
    label: <Link to="/wechat-accounts">公众号</Link>,
  },
  {
    key: "/wechat-account-groups",
    icon: <AppstoreOutlined />,
    label: <Link to="/wechat-account-groups">公众号分组</Link>,
  },
  { key: "/configs", icon: <SettingOutlined />, label: <Link to="/configs">配置</Link> },
];

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { user, logout, setUser } = useAuthStore();

  const userQuery = useQuery({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
  });

  useEffect(() => {
    if (userQuery.data) {
      setUser(userQuery.data);
    }
  }, [setUser, userQuery.data]);

  const menuItems = useMemo<MenuProps["items"]>(() => {
    const items = [...(baseMenuItems || [])];
    if (user?.role === "admin") {
      items.push({ key: "/sys", icon: <SettingOutlined />, label: <Link to="/sys">系统</Link> });
    }
    return items;
  }, [user?.role]);

  const selectedKey = useMemo(() => {
    const match = menuItems?.find((item: any) => location.pathname.startsWith(item.key));
    return match ? [String(match.key)] : ["/activities"];
  }, [location.pathname]);

  const userMenu: MenuProps["items"] = [
    { key: "profile", icon: <UserOutlined />, label: "用户资料" },
    { key: "password", icon: <SettingOutlined />, label: "修改密码" },
    { type: "divider" },
    { key: "logout", icon: <LogoutOutlined />, label: "退出登录" },
  ];

  const onUserMenuClick: MenuProps["onClick"] = async ({ key }) => {
    if (key === "profile") navigate("/profile");
    if (key === "password") navigate("/change-password");
    if (key === "logout") {
      try {
        await logoutApi();
      } catch {
        // best effort
      }
      logout();
      message.success("已退出登录");
      navigate("/login", { replace: true });
    }
  };

  return (
    <Layout className="app-shell">
      <Sider
        className="app-sidebar"
        theme="light"
        width={232}
        collapsedWidth={72}
        collapsed={collapsed}
      >
        <div className="app-logo">
          <div className="logo-mark">活</div>
          {!collapsed && <span>微信活动订阅助手</span>}
        </div>
        <Menu mode="inline" selectedKeys={selectedKey} items={menuItems} />
      </Sider>
      <Layout>
        <Header className="app-header">
          <div className="toolbar">
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((value) => !value)}
            />
            <Typography.Text strong>后台管理</Typography.Text>
          </div>
          <Dropdown menu={{ items: userMenu, onClick: onUserMenuClick }} trigger={["click"]}>
            <Button type="text">
              <Avatar size={28} icon={<UserOutlined />} /> {user?.nickname || user?.username || "账户"}
            </Button>
          </Dropdown>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
