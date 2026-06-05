import {
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Avatar, Button, Card, Input, Popconfirm, Space, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteWechatAccount,
  listWechatAccounts,
  syncWechatAccountArticles,
} from "@/api/wechatAccounts";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import type { WechatAccount } from "@/types/api";

export default function WechatAccountsPage() {
  const [page, setPage] = useState(1);
  const [kw, setKw] = useState("");
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const pageSize = 20;
  const query = useQuery({
    queryKey: ["wechat-accounts", page, kw],
    queryFn: () =>
      listWechatAccounts({ offset: (page - 1) * pageSize, limit: pageSize, kw }),
  });
  const sync = useMutation({
    mutationFn: (id: string) => syncWechatAccountArticles(id),
    onSuccess: () => message.success("已触发采集任务"),
  });
  const remove = useMutation({
    mutationFn: deleteWechatAccount,
    onSuccess: () => {
      message.success("公众号已删除");
      queryClient.invalidateQueries({ queryKey: ["wechat-accounts"] });
    },
  });

  const columns: ColumnsType<WechatAccount> = [
    {
      title: "公众号",
      dataIndex: "name",
      render: (_, record) => (
        <Space>
          <Avatar src={record.logo_url || record.mp_cover}>
            {(record.name || record.mp_name || "?").slice(0, 1)}
          </Avatar>
          <div>
            <div>{record.name || record.mp_name || record.id}</div>
            <small>{record.faker_id || record.id}</small>
          </div>
        </Space>
      ),
    },
    {
      title: "描述",
      dataIndex: "description",
      ellipsis: true,
      render: (_, record) => record.description || record.mp_intro || "-",
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (value) => <Tag color={value === 0 ? "default" : "success"}>{value === 0 ? "停用" : "启用"}</Tag>,
    },
    {
      title: "最近采集",
      dataIndex: "last_fetch",
      width: 180,
      render: (_, record) =>
        record.last_fetch ? dayjs(record.last_fetch).format("YYYY-MM-DD HH:mm") : "-",
    },
    {
      title: "操作",
      width: 210,
      render: (_, record) => (
        <Space>
          <Button type="text" icon={<SyncOutlined />} onClick={() => sync.mutate(record.id)}>
            采集
          </Button>
          <Tooltip title="复制公众号标识">
            <Button
              type="text"
              icon={<CopyOutlined />}
              onClick={() => {
                navigator.clipboard.writeText(record.faker_id || record.id);
                message.success("已复制");
              }}
            />
          </Tooltip>
          <Popconfirm title="删除这个公众号？" onConfirm={() => remove.mutate(record.id)}>
            <Button danger type="text" icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const rows = query.data?.list || [];
  return (
    <div className="page">
      <PageHeader
        title="公众号"
        subtitle="维护系统级公众号采集来源，普通用户无需分别扫码。"
        actions={
          <>
            <Input.Search
              allowClear
              placeholder="搜索公众号"
              style={{ width: 220 }}
              onSearch={(value) => {
                setKw(value.trim());
                setPage(1);
              }}
            />
            <Button icon={<ReloadOutlined />} onClick={() => query.refetch()}>
              刷新
            </Button>
            <Link to="/wechat-accounts/add">
              <Button type="primary" icon={<PlusOutlined />}>
                添加公众号
              </Button>
            </Link>
          </>
        }
      />
      <Card className="soft-card">
        <Table
          rowKey="id"
          loading={query.isLoading}
          columns={columns}
          dataSource={rows}
          locale={{ emptyText: <EmptyState description="暂无公众号" /> }}
          pagination={{
            current: page,
            pageSize,
            total: query.data?.total || 0,
            onChange: setPage,
            showSizeChanger: false,
          }}
        />
      </Card>
    </div>
  );
}
