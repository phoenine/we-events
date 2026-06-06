import { DeleteOutlined, PlusOutlined, SyncOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";
import {
  createWechatAccountGroup,
  deleteWechatAccountGroup,
  listWechatAccountGroups,
  syncWechatAccountGroupArticles,
  updateWechatAccountGroup,
} from "@/api/wechatAccountGroups";
import { listWechatAccounts } from "@/api/wechatAccounts";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import type { ApiList, WechatAccount, WechatAccountGroup } from "@/types/api";

function normalize(data: ApiList<WechatAccountGroup> | WechatAccountGroup[] | undefined) {
  if (!data) return [];
  return Array.isArray(data) ? data : data.list || [];
}

function parseGroupAccountIds(value: WechatAccountGroup["wechat_account_ids"]) {
  if (Array.isArray(value)) return value.map(String);
  if (!value) return [];
  try {
    const parsed = JSON.parse(String(value));
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

export default function WechatAccountGroupsPage() {
  const [editing, setEditing] = useState<WechatAccountGroup | null>(null);
  const [syncing, setSyncing] = useState<WechatAccountGroup | null>(null);
  const [form] = Form.useForm();
  const [syncForm] = Form.useForm();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const query = useQuery({ queryKey: ["wechat-account-groups"], queryFn: () => listWechatAccountGroups() });
  const accountsQuery = useQuery({
    queryKey: ["wechat-accounts", "group-options"],
    queryFn: () => listWechatAccounts({ offset: 0, limit: 100 }),
  });
  const save = useMutation({
    mutationFn: (values: Partial<WechatAccountGroup>) =>
      editing?.id ? updateWechatAccountGroup(editing.id, values) : createWechatAccountGroup(values),
    onSuccess: () => {
      message.success("分组已保存");
      setEditing(null);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["wechat-account-groups"] });
    },
  });
  const remove = useMutation({
    mutationFn: deleteWechatAccountGroup,
    onSuccess: () => {
      message.success("分组已删除");
      queryClient.invalidateQueries({ queryKey: ["wechat-account-groups"] });
    },
  });
  const syncGroup = useMutation({
    mutationFn: (values: { start_page?: number; end_page?: number }) =>
      syncWechatAccountGroupArticles(String(syncing?.id || ""), values),
    onSuccess: (data: any) => {
      const started = data?.started_account_ids?.length || 0;
      const skipped = data?.skipped_accounts?.length || 0;
      message.success(`已触发 ${started} 个公众号采集${skipped ? `，跳过 ${skipped} 个` : ""}`);
      setSyncing(null);
      syncForm.resetFields();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "分组采集失败"),
  });
  const accountNameById = new Map(
    (accountsQuery.data?.list || []).map((account: WechatAccount) => [
      account.id,
      account.name || account.mp_name || account.id,
    ])
  );

  const columns: ColumnsType<WechatAccountGroup> = [
    { title: "名称", dataIndex: "name", width: 180 },
    {
      title: "公众号",
      dataIndex: "wechat_account_ids",
      render: (_, record) => {
        const accountIds = parseGroupAccountIds(record.wechat_account_ids);
        if (!accountIds.length) return "-";
        return (
          <Space wrap size={[6, 6]}>
            {accountIds.map((accountId) => (
              <Tag key={accountId}>{accountNameById.get(accountId) || accountId}</Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: "公众号数",
      dataIndex: "wechat_account_count",
      width: 100,
      render: (_, record) => record.wechat_account_count ?? parseGroupAccountIds(record.wechat_account_ids).length,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (value) => <Tag color={value === 0 ? "default" : "success"}>{value === 0 ? "停用" : "启用"}</Tag>,
    },
    {
      title: "操作",
      width: 230,
      render: (_, record) => (
        <Space>
          <Button type="text" icon={<SyncOutlined />} onClick={() => setSyncing(record)}>
            采集
          </Button>
          <Button
            type="link"
            onClick={() => {
              setEditing(record);
              form.setFieldsValue({
                ...record,
                wechat_account_ids: parseGroupAccountIds(record.wechat_account_ids),
              });
            }}
          >
            编辑
          </Button>
          <Popconfirm title="删除这个分组？" onConfirm={() => remove.mutate(record.id)}>
            <Button danger type="text" icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="公众号分组"
        subtitle="按业务主题组织公众号来源。"
        actions={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              form.resetFields();
              setEditing({} as WechatAccountGroup);
            }}
          >
            新建分组
          </Button>
        }
      />
      <Card className="soft-card">
        <Table
          rowKey="id"
          loading={query.isLoading}
          columns={columns}
          dataSource={normalize(query.data)}
          locale={{ emptyText: <EmptyState description="暂无公众号分组" /> }}
        />
      </Card>
      <Modal
        title={editing?.id ? "编辑分组" : "新建分组"}
        open={!!editing}
        onCancel={() => {
          setEditing(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        confirmLoading={save.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(values) => save.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="wechat_account_ids" label="公众号">
            <Select
              mode="multiple"
              loading={accountsQuery.isLoading}
              placeholder="选择这个分组包含的公众号"
              optionFilterProp="label"
              options={(accountsQuery.data?.list || []).map((account) => ({
                value: account.id,
                label: account.name || account.mp_name || account.id,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={`采集分组：${syncing?.name || ""}`}
        open={!!syncing}
        okText="开始采集"
        cancelText="取消"
        confirmLoading={syncGroup.isPending}
        onCancel={() => {
          setSyncing(null);
          syncForm.resetFields();
        }}
        onOk={() => syncForm.submit()}
      >
        <Form
          form={syncForm}
          layout="vertical"
          initialValues={{ start_page: 0, end_page: 1 }}
          onFinish={(values) => syncGroup.mutate(values)}
        >
          <Form.Item name="start_page" label="起始页" rules={[{ required: true }]}>
            <InputNumber min={0} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="end_page" label="采集页数" rules={[{ required: true }]}>
            <InputNumber min={1} precision={0} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
