import { DeleteOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Card, Drawer, Popconfirm, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useState } from "react";
import { deleteActivity, fetchActivities, listActivities } from "@/api/activities";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import type { Activity } from "@/types/api";

export default function ActivitiesPage() {
  const [selected, setSelected] = useState<Activity | null>(null);
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const query = useQuery({ queryKey: ["activities"], queryFn: () => listActivities({ limit: 200 }) });
  const extract = useMutation({
    mutationFn: () => fetchActivities({ scope: "week", limit: 200 }),
    onSuccess: () => {
      message.success("活动抽取已完成");
      queryClient.invalidateQueries({ queryKey: ["activities"] });
    },
  });
  const remove = useMutation({
    mutationFn: deleteActivity,
    onSuccess: () => {
      message.success("活动已删除");
      queryClient.invalidateQueries({ queryKey: ["activities"] });
    },
  });
  const columns: ColumnsType<Activity> = [
    {
      title: "活动",
      dataIndex: "title",
      render: (value, record) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => setSelected(record)}>
          {value || "未命名活动"}
        </Button>
      ),
    },
    { title: "报名", dataIndex: "registration_time_text", ellipsis: true },
    { title: "时间", dataIndex: "event_time_text", ellipsis: true },
    { title: "费用", dataIndex: "event_fee", width: 120 },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value) => <Tag color={value === "active" ? "success" : "default"}>{value || "active"}</Tag>,
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 170,
      render: (value) => (value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "-"),
    },
    {
      title: "操作",
      width: 80,
      render: (_, record) => (
        <Popconfirm title="删除这个活动？" onConfirm={() => remove.mutate(record.id)}>
          <Button danger type="text" icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="活动"
        subtitle="从文章中抽取的活动信息，支持人工复核。"
        actions={
          <Button type="primary" icon={<ThunderboltOutlined />} loading={extract.isPending} onClick={() => extract.mutate()}>
            抽取本周活动
          </Button>
        }
      />
      <Card className="soft-card">
        <Table
          rowKey="id"
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data || []}
          locale={{ emptyText: <EmptyState description="暂无活动" /> }}
        />
      </Card>
      <Drawer title={selected?.title || "活动详情"} open={!!selected} onClose={() => setSelected(null)} width={560}>
        <Space direction="vertical" size={12}>
          <Typography.Text>报名：{selected?.registration_time_text || "-"}</Typography.Text>
          <Typography.Text>方式：{selected?.registration_method || "-"}</Typography.Text>
          <Typography.Text>时间：{selected?.event_time_text || "-"}</Typography.Text>
          <Typography.Text>费用：{selected?.event_fee || "-"}</Typography.Text>
          <Typography.Text>对象：{selected?.audience || "-"}</Typography.Text>
          <Typography.Link href={selected?.article_url} target="_blank">
            原文链接
          </Typography.Link>
        </Space>
      </Drawer>
    </div>
  );
}
