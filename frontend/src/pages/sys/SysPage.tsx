import { useQuery } from "@tanstack/react-query";
import { Card, Descriptions, Space, Statistic } from "antd";
import { getSysInfo, getSysResources } from "@/api/sys";
import PageHeader from "@/components/common/PageHeader";
import WechatQrCard from "@/components/common/WechatQrCard";

export default function SysPage() {
  const info = useQuery({ queryKey: ["sys-info"], queryFn: getSysInfo });
  const resources = useQuery({ queryKey: ["sys-resources"], queryFn: getSysResources, refetchInterval: 5000 });
  const data: any = info.data || {};
  const res: any = resources.data || {};
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
              {data.wx?.login ? "已登录" : "未登录"}
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
