import { DeleteOutlined, PlusOutlined, SyncOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tag, TimePicker, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import {
  createWechatAccountGroup,
  deleteWechatAccountGroup,
  listWechatAccountGroups,
  syncWechatAccountGroupArticles,
  updateWechatAccountGroup,
  updateWechatAccountGroupSchedule,
} from "@/api/wechatAccountGroups";
import { getArticleCollectionRun, listWechatAccounts } from "@/api/wechatAccounts";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import { useAuthStore } from "@/store/authStore";
import type { ApiList, WechatAccount, WechatAccountGroup } from "@/types/api";
import {
  addArticleCollectionRun,
  loadArticleCollectionRuns,
  removeArticleCollectionRuns,
} from "@/utils/articleCollectionRuns";
import {
  formatGroupCollectionSchedule,
  groupCollectionRunColor,
  groupCollectionRunLabel,
  hasGroupCollectionResult,
} from "@/utils/groupCollectionSchedule";

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
  const [scheduling, setScheduling] = useState<WechatAccountGroup | null>(null);
  const [activeCollectionRuns, setActiveCollectionRuns] = useState(loadArticleCollectionRuns);
  const [form] = Form.useForm();
  const [syncForm] = Form.useForm();
  const [scheduleForm] = Form.useForm();
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((state) => state.user);
  const { message } = App.useApp();
  const query = useQuery({
    queryKey: ["wechat-account-groups"],
    queryFn: () => listWechatAccountGroups(),
    refetchInterval: 30_000,
  });
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
      if (data?.run_id) {
        addArticleCollectionRun({ runId: data.run_id });
        setActiveCollectionRuns((runs) => {
          if (runs.some((item) => item.runId === data.run_id)) return runs;
          return [...runs, { runId: data.run_id }];
        });
      }
      const started = data?.started_account_ids?.length || 0;
      const skipped = data?.skipped_accounts?.length || 0;
      message.success(`已加入队列 ${started} 个公众号${skipped ? `，跳过 ${skipped} 个` : ""}`);
      setSyncing(null);
      syncForm.resetFields();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "分组采集失败"),
  });
  const saveSchedule = useMutation({
    mutationFn: (values: { enabled: boolean; time?: dayjs.Dayjs | null; collection_pages: number }) =>
      updateWechatAccountGroupSchedule(String(scheduling?.id || ""), {
        enabled: values.enabled,
        time: values.time ? values.time.format("HH:mm") : null,
        collection_pages: values.collection_pages,
      }),
    onSuccess: () => {
      message.success("定时采集设置已保存");
      setScheduling(null);
      scheduleForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ["wechat-account-groups"] });
    },
    onError: (error) =>
      message.error(error instanceof Error ? error.message : "定时采集设置保存失败"),
  });
  useEffect(() => {
    if (!activeCollectionRuns.length) return;

    const timer = window.setInterval(async () => {
      const finishedRunIds = new Set<string>();
      await Promise.all(
        activeCollectionRuns.map(async (item) => {
          try {
            const run: any = await getArticleCollectionRun(item.runId);
            if (["queued", "processing"].includes(run?.status)) return;
            finishedRunIds.add(item.runId);
            if (run?.status === "success" || run?.status === "partial_success") {
              message.success(`文章采集完成${run?.articles_count ? `，采集 ${run.articles_count} 篇` : ""}`);
            } else if (run?.status === "failed") {
              message.error(run?.error || "文章采集失败");
            }
          } catch {
            finishedRunIds.add(item.runId);
          }
        })
      );
      if (finishedRunIds.size) {
        setActiveCollectionRuns(removeArticleCollectionRuns(finishedRunIds));
        queryClient.invalidateQueries({ queryKey: ["wechat-account-groups"] });
        queryClient.invalidateQueries({ queryKey: ["wechat-accounts"] });
        queryClient.invalidateQueries({ queryKey: ["articles"] });
      }
    }, 3000);

    return () => window.clearInterval(timer);
  }, [activeCollectionRuns, message, queryClient]);

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
      title: "定时采集",
      width: 150,
      render: (_, record) => {
        return <span>{formatGroupCollectionSchedule(record)}</span>;
      },
    },
    {
      title: "采集结果",
      width: 190,
      render: (_, record) => {
        if (!hasGroupCollectionResult(record)) return "-";
        const runLabel = groupCollectionRunLabel(
          record.last_collection_run,
          record.last_schedule_error
        );
        const lastTime = record.last_scheduled_at
          ? dayjs(record.last_scheduled_at).format("YYYY-MM-DD HH:mm")
          : "";
        return (
          <Tooltip title={record.last_schedule_error || record.last_collection_run?.error}>
            <Space size={4}>
              <Tag
                color={groupCollectionRunColor(
                  record.last_collection_run,
                  record.last_schedule_error
                )}
              >
                {runLabel}
              </Tag>
              {lastTime && <Typography.Text type="secondary">{lastTime}</Typography.Text>}
            </Space>
          </Tooltip>
        );
      },
    },
    {
      title: "操作",
      width: 300,
      render: (_, record) => (
        <Space>
          <Button type="text" icon={<SyncOutlined />} onClick={() => setSyncing(record)}>
            采集
          </Button>
          {currentUser?.role === "admin" && (
            <Button
              type="text"
              onClick={() => {
                setScheduling(record);
                scheduleForm.setFieldsValue({
                  enabled: Boolean(record.schedule_enabled),
                  time: record.schedule_time
                    ? dayjs(`2000-01-01T${record.schedule_time}`)
                    : null,
                  collection_pages: record.collection_pages || 1,
                });
              }}
            >
              定时设置
            </Button>
          )}
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
          <>
            {activeCollectionRuns.length > 0 && <Tag color="processing">采集中 {activeCollectionRuns.length}</Tag>}
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
          </>
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
      <Modal
        title={`定时采集：${scheduling?.name || ""}`}
        open={!!scheduling}
        okText="保存"
        cancelText="取消"
        confirmLoading={saveSchedule.isPending}
        onCancel={() => {
          setScheduling(null);
          scheduleForm.resetFields();
        }}
        onOk={() => scheduleForm.submit()}
      >
        <Form
          form={scheduleForm}
          layout="vertical"
          initialValues={{ enabled: false, collection_pages: 1 }}
          onFinish={(values) => saveSchedule.mutate(values)}
        >
          <Form.Item name="enabled" label="启用定时采集" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, next) => prev.enabled !== next.enabled}>
            {({ getFieldValue }) => (
              <Form.Item
                name="time"
                label="每日执行时间"
                rules={[
                  {
                    required: Boolean(getFieldValue("enabled")),
                    message: "请选择执行时间",
                  },
                ]}
              >
                <TimePicker format="HH:mm" style={{ width: "100%" }} />
              </Form.Item>
            )}
          </Form.Item>
          <Form.Item
            name="collection_pages"
            label="采集页数"
            rules={[{ required: true, message: "请输入采集页数" }]}
          >
            <InputNumber min={1} max={5} precision={0} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
