import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Card, Form, Input, Modal, Space, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";
import { listConfigs, updateConfig } from "@/api/configs";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import type { ConfigItem } from "@/types/api";

export default function ConfigsPage() {
  const [editing, setEditing] = useState<ConfigItem | null>(null);
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["configs"], queryFn: () => listConfigs() });
  const save = useMutation({
    mutationFn: (values: Partial<ConfigItem>) => updateConfig(editing!.key, values),
    onSuccess: () => {
      message.success("配置已保存");
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["configs"] });
    },
  });
  const columns: ColumnsType<ConfigItem> = [
    { title: "Key", dataIndex: "key", width: 220 },
    { title: "Value", dataIndex: "value", render: (value) => String(value ?? "") },
    { title: "描述", dataIndex: "description", ellipsis: true },
    {
      title: "操作",
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          onClick={() => {
            setEditing(record);
            form.setFieldsValue({ ...record, value: String(record.value ?? "") });
          }}
        >
          编辑
        </Button>
      ),
    },
  ];
  return (
    <div className="page">
      <PageHeader title="配置" subtitle="管理后端运行配置项。" />
      <Card className="soft-card">
        <Table
          rowKey="key"
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data || []}
          locale={{ emptyText: <EmptyState description="暂无配置" /> }}
        />
      </Card>
      <Modal
        title={`编辑配置 ${editing?.key || ""}`}
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={() => form.submit()}
        confirmLoading={save.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(values) => save.mutate(values)}>
          <Form.Item name="value" label="Value">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input />
          </Form.Item>
        </Form>
        <Space />
      </Modal>
    </div>
  );
}
