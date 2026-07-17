import { useQuery } from "@tanstack/react-query";
import { InfoCircleOutlined } from "@ant-design/icons";
import { Card } from "antd";
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

function authStatusMeta(status?: string, state?: string) {
  if (state === "waiting") return { color: "processing", label: "等待中" };
  if (state === "failed") return { color: "default", label: "未授权" };
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
  const wxAuthMeta = authStatusMeta(wxAuth.status, wxAuth.state);
  const authLabel = ["waiting", "failed"].includes(wxAuth.state) ? wxAuthMeta.label : wxAuth.label || wxAuthMeta.label;
  const runtimeRows = [
    { label: "API", value: data.api_version || "-" },
    { label: "Core", value: data.core_version || "-" },
    { label: "授权状态", value: wxAuth.message || "-" },
    { label: "过期时间", value: wxAuth.expires_at || "-" },
    { label: "剩余时间", value: formatRemaining(wxAuth.remaining_seconds) },
    { label: "运行状态", value: wxAuth.state || "-" },
  ];
  const systemStats = [
    {
      label: "CPU",
      description: "当前计算占用",
      value: `${res.cpu?.percent || 0}%`,
      tone: "blue",
    },
    {
      label: "Memory",
      description: "当前内存占用",
      value: `${res.memory?.percent || 0}%`,
      tone: "purple",
    },
    {
      label: "Queue",
      description: "等待中的任务",
      value: res.queue?.pending_tasks || 0,
      tone: "amber",
    },
    {
      label: "微信登录",
      description: wxAuth.message || "公众号授权状态",
      value: wxAuthMeta.label,
      tone: wxAuthMeta.color === "success" ? "green" : "amber",
    },
  ];
  return (
    <div className="page">
      <PageHeader title="系统信息" subtitle="查看后端运行状态、微信登录态和任务队列。" />
      <div className="wechat-stats">
        {systemStats.map((item) => (
          <Card key={item.label} className="stat-card">
            <div className={`stat-value-block stat-value-${item.tone}`}>{item.value}</div>
            <div>
              <div className="stat-label">{item.label}</div>
              <div className="stat-description">{item.description}</div>
            </div>
          </Card>
        ))}
      </div>
      <div className="system-card-grid">
        <WechatQrCard
          statusColor={wxAuthMeta.color}
          statusLabel={authLabel}
          statusMessage={
            wxAuthMeta.color === "success"
              ? "当前可正常采集。微信登录态无法永久保活，过期或采集失败时重新扫码。"
              : "请重新扫码完成公众号授权，授权后系统会自动更新采集登录态。"
          }
        />
        <div className="system-runtime-column">
          <Card className="soft-card system-info-card" loading={info.isLoading} title="运行详情">
            <div className="system-detail-list">
              {runtimeRows.map((row) => (
                <div className="system-detail-row" key={row.label}>
                  <span className="system-detail-label">{row.label}</span>
                  <span className="system-detail-value">{row.value}</span>
                </div>
              ))}
            </div>
          </Card>
          <div className="system-inline-tip">
            <InfoCircleOutlined />
            <div>
              <strong>系统页只展示运行态</strong>
              <span>版本、授权、资源和队列信息会自动刷新；具体采集与抽取操作在对应业务页面完成。</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
