import { useQuery } from "@tanstack/react-query";
import { Card, Descriptions, Space, Statistic, Tag, Typography } from "antd";
import { getSysInfo, getSysResources } from "@/api/sys";
import PageHeader from "@/components/common/PageHeader";
import WechatQrCard from "@/components/common/WechatQrCard";

function formatRemaining(seconds?: number) {
  if (!seconds || seconds <= 0) return "-";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days} 天 ${hours} 小时`;
  if (hours > 0) return `${hours} 小时 ${minutes} 分钟`;
  return `${minutes} 分钟`;
}

function authStatusMeta(status?: string) {
  if (status === "authorized") return { color: "success", label: "已授权" };
  if (status === "expired") return { color: "error", label: "已过期" };
  if (status === "pending") return { color: "processing", label: "授权中" };
  if (status === "error") return { color: "error", label: "授权异常" };
  return { color: "default", label: "未授权" };
}

export default function SysPage() {
  const info = useQuery({ queryKey: ["sys-info"], queryFn: getSysInfo, refetchInterval: 30_000 });
  const resources = useQuery({ queryKey: ["sys-resources"], queryFn: getSysResources, refetchInterval: 5000 });
  const data: any = info.data || {};
  const res: any = resources.data || {};
  const wxAuth = data.wx?.auth || {};
  const wxAuthMeta = authStatusMeta(wxAuth.status);
  return (
    <div className="page">
      <PageHeader title="系统信息" subtitle="查看后端运行状态、微信登录态和任务队列。" />
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <WechatQrCard />
        <Card className="soft-card" loading={info.isLoading}>
          <Descriptions column={2}>
            <Descriptions.Item label="API">{data.api_version}</Descriptions.Item>
            <Descriptions.Item label="Core">{data.core_version}</Descriptions.Item>
            <Descriptions.Item label="Python">{data.python_version}</Descriptions.Item>
            <Descriptions.Item label="微信登录">
              <Tag color={wxAuthMeta.color}>{wxAuth.label || wxAuthMeta.label}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="授权状态">{wxAuth.message || "-"}</Descriptions.Item>
            <Descriptions.Item label="过期时间">{wxAuth.expires_at || "-"}</Descriptions.Item>
            <Descriptions.Item label="剩余时间">{formatRemaining(wxAuth.remaining_seconds)}</Descriptions.Item>
            <Descriptions.Item label="运行状态">{wxAuth.state || "-"}</Descriptions.Item>
            <Descriptions.Item label="建议">
              <Typography.Text type={wxAuth.status === "authorized" ? "secondary" : "danger"}>
                {wxAuth.status === "authorized"
                  ? "当前可正常采集。微信登录态无法保证永久保活，建议在过期或采集失败时重新扫码。"
                  : "请使用上方二维码重新完成公众号扫码授权。"}
              </Typography.Text>
            </Descriptions.Item>
          </Descriptions>
        </Card>
        <Space wrap>
          <Card className="soft-card">
            <Statistic title="CPU" value={res.cpu?.percent || 0} suffix="%" />
          </Card>
          <Card className="soft-card">
            <Statistic title="Memory" value={res.memory?.percent || 0} suffix="%" />
          </Card>
          <Card className="soft-card">
            <Statistic title="Queue Pending" value={res.queue?.pending_tasks || 0} />
          </Card>
        </Space>
      </Space>
    </div>
  );
}
