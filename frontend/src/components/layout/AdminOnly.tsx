import type { ReactNode } from "react";
import { useEffect } from "react";
import { Alert, Card } from "antd";
import { useQuery } from "@tanstack/react-query";
import { getCurrentUser } from "@/api/user";
import { useAuthStore } from "@/store/authStore";

export default function AdminOnly({ children }: { children: ReactNode }) {
  const { user, setUser } = useAuthStore();
  const query = useQuery({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
    enabled: !user,
  });

  useEffect(() => {
    if (query.data && !user) {
      setUser(query.data);
    }
  }, [query.data, setUser, user]);

  const currentUser = user || query.data;
  if (!currentUser) {
    return <Card loading />;
  }

  if (currentUser.role !== "admin") {
    return (
      <Card className="soft-card">
        <Alert
          type="warning"
          showIcon
          message="无权访问"
          description="该页面仅管理员可访问。"
        />
      </Card>
    );
  }

  return children;
}
