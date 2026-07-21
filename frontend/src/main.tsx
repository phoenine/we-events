import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, App as AntdApp } from "antd";
import zhCN from "antd/locale/zh_CN";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/app/App";
import "@/styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#2563EB",
          borderRadius: 8,
          colorText: "#111827",
          colorTextSecondary: "#667085",
          colorBorder: "#E5E7EB",
          colorBgLayout: "#F5F7FB",
          fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        },
        components: {
          Card: { borderRadiusLG: 12 },
          Button: { borderRadius: 8 },
          Menu: {
            itemBorderRadius: 10,
            itemHeight: 44,
            itemSelectedBg: "#EFF6FF",
            itemSelectedColor: "#1D4ED8",
          },
        },
      }}
    >
      <AntdApp>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>
);
