import { ClockCircleOutlined, DeleteOutlined, EditOutlined, PlusOutlined, SyncOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Tag, TimePicker, Tooltip, Typography } from "antd";
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
  const groups = normalize(query.data);
  const enabledGroupCount = groups.filter((group) => group.status !== 0).length;
  const coveredAccountCount = groups.reduce(
    (total, group) =>
      total + (group.wechat_account_count ?? parseGroupAccountIds(group.wechat_account_ids).length),
    0
  );

  const openSchedule = (record: WechatAccountGroup) => {
    setScheduling(record);
    scheduleForm.setFieldsValue({
      enabled: Boolean(record.schedule_enabled),
      time: record.schedule_time
        ? dayjs(`2000-01-01T${record.schedule_time}`)
        : null,
      collection_pages: record.collection_pages || 1,
    });
  };

  const openEdit = (record: WechatAccountGroup) => {
    setEditing(record);
    form.setFieldsValue({
      ...record,
      wechat_account_ids: parseGroupAccountIds(record.wechat_account_ids),
    });
  };

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
      <div className="wechat-stats">
        {[
          { label: "分组数", description: "当前业务来源集合", value: groups.length, tone: "blue" },
          { label: "启用中", description: "可参与采集的分组", value: enabledGroupCount, tone: "green" },
          { label: "覆盖来源", description: "分组内公众号数量", value: coveredAccountCount, tone: "purple" },
          { label: "采集中", description: "正在执行的采集任务", value: activeCollectionRuns.length, tone: "amber" },
        ].map((item) => (
          <Card key={item.label} className="stat-card">
            <div className={`stat-value-block stat-value-${item.tone}`}>{item.value}</div>
            <div>
              <div className="stat-label">{item.label}</div>
              <div className="stat-description">{item.description}</div>
            </div>
          </Card>
        ))}
      </div>
      <Card
        className="soft-card source-list-panel"
        title="分组列表"
        extra={<span className="panel-count">共 {groups.length} 个分组</span>}
        loading={query.isLoading}
      >
        {groups.length ? (
          <div className="group-card-grid">
            {groups.map((group) => {
              const accountIds = parseGroupAccountIds(group.wechat_account_ids);
              const runLabel = hasGroupCollectionResult(group)
                ? groupCollectionRunLabel(group.last_collection_run, group.last_schedule_error)
                : "暂无结果";
              const lastTime = group.last_scheduled_at
                ? dayjs(group.last_scheduled_at).format("YYYY-MM-DD HH:mm")
                : "";

              return (
                <Card key={group.id} className="source-card group-card" hoverable>
                  <div className="group-card-head">
                    <div className="group-card-title">
                      <div className="source-name">{group.name}</div>
                      <div className="source-id">{formatGroupCollectionSchedule(group)}</div>
                    </div>
                    <Tag color={group.schedule_enabled ? "success" : "default"}>
                      {group.schedule_enabled ? "已启用" : "未启用"}
                    </Tag>
                  </div>

                  <div className="group-account-tags">
                    {accountIds.length ? (
                      accountIds.slice(0, 8).map((accountId) => (
                        <Tag key={accountId}>{accountNameById.get(accountId) || accountId}</Tag>
                      ))
                    ) : (
                      <Typography.Text type="secondary">暂无公众号</Typography.Text>
                    )}
                    {accountIds.length > 8 && <Tag>+{accountIds.length - 8}</Tag>}
                  </div>

                  <div className="group-result-row">
                    <Tooltip title={group.last_schedule_error || group.last_collection_run?.error}>
                      <Tag
                        color={
                          hasGroupCollectionResult(group)
                            ? groupCollectionRunColor(group.last_collection_run, group.last_schedule_error)
                            : "default"
                        }
                      >
                        {runLabel}
                      </Tag>
                    </Tooltip>
                    {lastTime && <span className="source-last-fetch">{lastTime}</span>}
                  </div>

                  <div className="source-card-bottom">
                    <span className="source-last-fetch">
                      {group.wechat_account_count ?? accountIds.length} 个公众号
                    </span>
                    <Space size={8} wrap>
                      <Button size="small" className="source-action-main" icon={<SyncOutlined />} onClick={() => setSyncing(group)}>
                        采集
                      </Button>
                      {currentUser?.role === "admin" && (
                        <Button size="small" className="source-action-main" icon={<ClockCircleOutlined />} onClick={() => openSchedule(group)}>
                          定时
                        </Button>
                      )}
                      <Button size="small" className="source-action-main" icon={<EditOutlined />} onClick={() => openEdit(group)}>
                        编辑
                      </Button>
                      <Popconfirm title="删除这个分组？" onConfirm={() => remove.mutate(group.id)}>
                        <Button danger size="small" className="source-icon-button" icon={<DeleteOutlined />} />
                      </Popconfirm>
                    </Space>
                  </div>
                </Card>
              );
            })}
          </div>
        ) : (
          <EmptyState description="暂无公众号分组" />
        )}
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
