import {
  ClearOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Card,
  Drawer,
  Form,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { TableRowSelection } from "antd/es/table/interface";
import type { ColumnsType } from "antd/es/table";
import DOMPurify from "dompurify";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  cleanArticles,
  cleanDuplicateArticles,
  cleanExpiredArticles,
  deleteArticle,
  deleteArticlesBatch,
  listArticles,
} from "@/api/articles";
import { extractArticleActivities, getActivityExtractionRun } from "@/api/activities";
import { listWechatAccounts, syncWechatAccountArticles } from "@/api/wechatAccounts";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import type { Article } from "@/types/api";
import {
  addActivityExtractionRun,
  loadActivityExtractionRuns,
  removeActivityExtractionRuns,
} from "@/utils/activityExtractionRuns";
import { formatEpochSeconds } from "@/utils/time";

export default function ArticlesPage() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [wechatAccountId, setWechatAccountId] = useState<string>();
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [selected, setSelected] = useState<Article | null>(null);
  const [extractingArticleId, setExtractingArticleId] = useState<string>();
  const [activeExtractionRuns, setActiveExtractionRuns] = useState(loadActivityExtractionRuns);
  const [syncOpen, setSyncOpen] = useState(false);
  const [syncForm] = Form.useForm();
  const queryClient = useQueryClient();
  const { message, modal } = App.useApp();
  const query = useQuery({
    queryKey: ["articles", page, pageSize, wechatAccountId],
    queryFn: () =>
      listArticles({
        offset: (page - 1) * pageSize,
        limit: pageSize,
        wechat_account_id: wechatAccountId,
      }),
  });
  const accountsQuery = useQuery({
    queryKey: ["wechat-accounts", "article-filter"],
    queryFn: () => listWechatAccounts({ offset: 0, limit: 100 }),
  });
  const remove = useMutation({
    mutationFn: deleteArticle,
    onSuccess: () => {
      message.success("文章已删除");
      queryClient.invalidateQueries({ queryKey: ["articles"] });
    },
  });
  const batchRemove = useMutation({
    mutationFn: deleteArticlesBatch,
    onSuccess: (data: any) => {
      message.success(`批量删除完成${data?.deleted_count ? `，成功 ${data.deleted_count} 篇` : ""}`);
      setSelectedRowKeys([]);
      queryClient.invalidateQueries({ queryKey: ["articles"] });
    },
  });
  const syncArticles = useMutation({
    mutationFn: (values: { start_page?: number; end_page?: number }) =>
      syncWechatAccountArticles(wechatAccountId || "", values),
    onSuccess: () => {
      message.success("已触发采集任务");
      setSyncOpen(false);
      syncForm.resetFields();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "触发采集失败"),
  });
  const cleanAction = useMutation({
    mutationFn: (type: "orphan" | "duplicate" | "expired") => {
      if (type === "duplicate") return cleanDuplicateArticles();
      if (type === "expired") return cleanExpiredArticles();
      return cleanArticles();
    },
    onSuccess: (data: any) => {
      message.success(data?.message || "清理完成");
      queryClient.invalidateQueries({ queryKey: ["articles"] });
    },
  });
  const extractActivity = useMutation({
    mutationFn: extractArticleActivities,
    onMutate: (articleId) => setExtractingArticleId(articleId),
    onSuccess: (data: any) => {
      if (data?.run_id) {
        addActivityExtractionRun({ runId: data.run_id, articleId: data.article_id });
        setActiveExtractionRuns((runs) => {
          if (runs.some((item) => item.runId === data.run_id)) return runs;
          return [...runs, { runId: data.run_id, articleId: data.article_id }];
        });
      }
      message.success(data?.already_running ? "活动抽取任务正在进行中" : "已开始活动抽取");
      queryClient.invalidateQueries({ queryKey: ["articles"] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "活动抽取失败"),
    onSettled: () => setExtractingArticleId(undefined),
  });

  useEffect(() => {
    if (!activeExtractionRuns.length) return;

    const timer = window.setInterval(async () => {
      const finishedRunIds = new Set<string>();
      await Promise.all(
        activeExtractionRuns.map(async (item) => {
          try {
            const run: any = await getActivityExtractionRun(item.runId);
            if (run?.status === "processing") return;

            finishedRunIds.add(item.runId);
            if (run?.status === "success") {
              message.success("活动抽取完成");
            } else if (run?.status === "not_activity") {
              message.info("未识别到活动");
            } else if (run?.status === "fallback_required") {
              message.warning(run?.error || "活动抽取需要兜底处理");
            } else if (run?.status === "failed") {
              message.error(run?.error || "活动抽取失败");
            }
          } catch (error) {
            finishedRunIds.add(item.runId);
            message.error(error instanceof Error ? error.message : "获取抽取任务状态失败");
          }
        })
      );

      if (finishedRunIds.size) {
        setActiveExtractionRuns(removeActivityExtractionRuns(finishedRunIds));
        queryClient.invalidateQueries({ queryKey: ["articles"] });
        queryClient.invalidateQueries({ queryKey: ["activities"] });
      }
    }, 2500);

    return () => window.clearInterval(timer);
  }, [activeExtractionRuns, message, queryClient]);

  const confirmClean = (type: "orphan" | "duplicate" | "expired", title: string) => {
    modal.confirm({
      title,
      content: "该操作会直接删除匹配文章及关联图片映射，请确认后继续。",
      okText: "确认清理",
      okButtonProps: { danger: true },
      onOk: () => cleanAction.mutateAsync(type),
    });
  };

  const rowSelection: TableRowSelection<Article> = {
    selectedRowKeys,
    onChange: setSelectedRowKeys,
  };
  const activeExtractionArticleIds = useMemo(
    () => new Set(activeExtractionRuns.map((item) => item.articleId)),
    [activeExtractionRuns]
  );
  const renderExtractionStatus = (value?: string) => {
    const colorMap: Record<string, string> = {
      pending: "default",
      processing: "processing",
      extracted: "success",
      not_activity: "default",
      failed: "error",
      fallback_required: "warning",
    };
    const status = value || "pending";
    return <Tag color={colorMap[status] || "default"}>{status}</Tag>;
  };

  const columns: ColumnsType<Article> = [
    {
      title: "标题",
      dataIndex: "title",
      ellipsis: true,
      render: (value, record) => (
        <Button type="link" className="article-title-button" onClick={() => setSelected(record)}>
          {value || "无标题"}
        </Button>
      ),
    },
    { title: "公众号", dataIndex: "mp_name", width: 190, ellipsis: true },
    {
      title: "发布时间",
      dataIndex: "publish_time",
      width: 170,
      render: (value) => formatEpochSeconds(value),
    },
    {
      title: "活动抽取",
      dataIndex: "activity_extraction_status",
      width: 120,
      render: renderExtractionStatus,
    },
    {
      title: "操作",
      width: 150,
      render: (_, record) => (
        <Space size={4}>
          <Button
            type="text"
            icon={<ThunderboltOutlined />}
            loading={
              (extractingArticleId === record.id && extractActivity.isPending) ||
              activeExtractionArticleIds.has(record.id)
            }
            disabled={
              record.activity_extraction_status === "processing" ||
              activeExtractionArticleIds.has(record.id)
            }
            onClick={() => extractActivity.mutate(record.id)}
          >
            抽取
          </Button>
          <Popconfirm title="删除这篇文章？" onConfirm={() => remove.mutate(record.id)}>
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
        title="文章"
        subtitle="查看已采集的公众号文章，并跟踪活动抽取状态。"
        actions={
          <>
            <Select
              allowClear
              showSearch
              placeholder="选择公众号"
              style={{ minWidth: 220 }}
              value={wechatAccountId}
              loading={accountsQuery.isLoading}
              optionFilterProp="label"
              onChange={(value) => {
                setWechatAccountId(value);
                setPage(1);
                setSelectedRowKeys([]);
              }}
              options={(accountsQuery.data?.list || []).map((account) => ({
                value: account.id,
                label: account.name || account.mp_name || account.id,
              }))}
            />
            <Button
              icon={<SyncOutlined />}
              disabled={!wechatAccountId}
              onClick={() => setSyncOpen(true)}
            >
              采集文章
            </Button>
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
        <Space wrap style={{ marginBottom: 12 }}>
          <Popconfirm
            title={`删除选中的 ${selectedRowKeys.length} 篇文章？`}
            onConfirm={() => batchRemove.mutate(selectedRowKeys.map(String))}
            okButtonProps={{ danger: true }}
          >
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={!selectedRowKeys.length}
              loading={batchRemove.isPending}
            >
              批量删除
            </Button>
          </Popconfirm>
          <Button
            icon={<ClearOutlined />}
            loading={cleanAction.isPending}
            onClick={() => confirmClean("orphan", "清理无效文章？")}
          >
            清理无效
          </Button>
          <Button
            icon={<ClearOutlined />}
            loading={cleanAction.isPending}
            onClick={() => confirmClean("duplicate", "清理重复文章？")}
          >
            清理重复
          </Button>
          <Button
            icon={<ClearOutlined />}
            loading={cleanAction.isPending}
            onClick={() => confirmClean("expired", "清理 15 天前文章？")}
          >
            清理过期
          </Button>
        </Space>
        <Table
          rowKey="id"
          rowSelection={rowSelection}
          loading={query.isLoading}
          columns={columns}
          dataSource={rows}
          locale={{ emptyText: <EmptyState description="暂无文章" /> }}
          pagination={{
            current: page,
            pageSize,
            total: query.data?.total || 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 篇文章`,
            pageSizeOptions: [10, 20, 50, 100],
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
              setSelectedRowKeys([]);
            },
          }}
        />
      </Card>
      <Modal
        title="采集文章"
        open={syncOpen}
        okText="开始采集"
        cancelText="取消"
        confirmLoading={syncArticles.isPending}
        onCancel={() => setSyncOpen(false)}
        onOk={() => syncForm.submit()}
      >
        <Form
          form={syncForm}
          layout="vertical"
          initialValues={{ start_page: 0, end_page: 1 }}
          onFinish={(values) => syncArticles.mutate(values)}
        >
          <Form.Item label="公众号">
            <Typography.Text>
              {(accountsQuery.data?.list || []).find((item) => item.id === wechatAccountId)?.name ||
                (accountsQuery.data?.list || []).find((item) => item.id === wechatAccountId)
                  ?.mp_name ||
                wechatAccountId}
            </Typography.Text>
          </Form.Item>
          <Form.Item name="start_page" label="起始页" rules={[{ required: true }]}>
            <InputNumber min={0} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="end_page" label="采集页数" rules={[{ required: true }]}>
            <InputNumber min={1} precision={0} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
      <Drawer
        title={selected?.title || "文章详情"}
        width={760}
        open={!!selected}
        onClose={() => setSelected(null)}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Typography.Text type="secondary">{selected?.url || selected?.link}</Typography.Text>
          <div
            className="article-content"
            dangerouslySetInnerHTML={{
              __html: DOMPurify.sanitize(selected?.content || selected?.content_md || "暂无正文"),
            }}
          />
        </Space>
      </Drawer>
    </div>
  );
}
