import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Card, Form, Input, Modal, Popconfirm, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";
import {
  createWechatAccountGroup,
  deleteWechatAccountGroup,
  listWechatAccountGroups,
  updateWechatAccountGroup,
} from "@/api/wechatAccountGroups";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import type { ApiList, WechatAccountGroup } from "@/types/api";

function normalize(data: ApiList<WechatAccountGroup> | WechatAccountGroup[] | undefined) {
  if (!data) return [];
  return Array.isArray(data) ? data : data.list || [];
}

export default function WechatAccountGroupsPage() {
  const [editing, setEditing] = useState<WechatAccountGroup | null>(null);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const query = useQuery({ queryKey: ["wechat-account-groups"], queryFn: () => listWechatAccountGroups() });
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

  const columns: ColumnsType<WechatAccountGroup> = [
    { title: "名称", dataIndex: "name" },
    { title: "描述", dataIndex: "description", ellipsis: true },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (value) => <Tag color={value === 0 ? "default" : "success"}>{value === 0 ? "停用" : "启用"}</Tag>,
    },
    {
      title: "操作",
      width: 150,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            onClick={() => {
              setEditing(record);
              form.setFieldsValue(record);
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
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing({} as WechatAccountGroup)}>
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
        onCancel={() => setEditing(null)}
        onOk={() => form.submit()}
        confirmLoading={save.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(values) => save.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
