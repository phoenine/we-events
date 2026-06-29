import {
  ClearOutlined,
  DeleteOutlined,
  RocketOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Card,
  Drawer,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { TableProps } from "antd";
import type { TableRowSelection } from "antd/es/table/interface";
import type { ColumnsType } from "antd/es/table";
import DOMPurify from "dompurify";
import { useEffect, useMemo, useState } from "react";
import {
  cleanArticles,
  cleanDuplicateArticles,
  cleanExpiredArticles,
  deleteArticle,
  deleteArticlesBatch,
  listArticles,
} from "@/api/articles";
import {
  extractArticleActivities,
  extractPendingActivities,
  getActivityExtractionRun,
  getActivityExtractionSummary,
} from "@/api/activities";
import {
  getArticleCollectionRun,
  listWechatAccounts,
} from "@/api/wechatAccounts";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import type { ApiList, Article } from "@/types/api";
import {
  addActivityExtractionRun,
  loadActivityExtractionRuns,
  removeActivityExtractionRuns,
} from "@/utils/activityExtractionRuns";
import {
  activityExtractionBatchButtonText,
  activityExtractionBatchConfirmation,
  shouldPollActivityExtraction,
} from "@/utils/activityExtractionBatch";
import {
  loadArticleCollectionRuns,
  removeArticleCollectionRuns,
} from "@/utils/articleCollectionRuns";
import {
  FILTERABLE_ACTIVITY_EXTRACTION_STATUSES,
  buildArticleListParams,
  type ArticleSortField,
  type SortOrder,
} from "@/utils/articleTableQuery";
import { removeIdsFromApiList } from "@/utils/optimisticDelete";
import { formatEpochSeconds } from "@/utils/time";

const articleCleanupMessageKey = "article-cleanup";

function toAntSortOrder(order: SortOrder) {
  return order === "asc" ? ("ascend" as const) : ("descend" as const);
}

export default function ArticlesPage() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [wechatAccountId, setWechatAccountId] = useState<string>();
  const [activityExtractionStatus, setActivityExtractionStatus] = useState<string>();
  const [sortBy, setSortBy] = useState<ArticleSortField>("publish_time");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [selected, setSelected] = useState<Article | null>(null);
  const [extractingArticleId, setExtractingArticleId] = useState<string>();
  const [watchingBatchExtraction, setWatchingBatchExtraction] = useState(false);
  const [activeExtractionRuns, setActiveExtractionRuns] = useState(loadActivityExtractionRuns);
  const [activeCollectionRuns, setActiveCollectionRuns] = useState(loadArticleCollectionRuns);
  const queryClient = useQueryClient();
  const { message, modal } = App.useApp();
  const query = useQuery({
    queryKey: [
      "articles",
      page,
      pageSize,
      wechatAccountId,
      activityExtractionStatus,
      sortBy,
      sortOrder,
    ],
    queryFn: () =>
      listArticles(buildArticleListParams({
        offset: (page - 1) * pageSize,
        limit: pageSize,
        wechatAccountId,
        activityExtractionStatus,
        sortBy,
        sortOrder,
      })),
  });
  const extractionSummaryQuery = useQuery({
    queryKey: ["activity-extraction-summary"],
    queryFn: getActivityExtractionSummary,
    refetchInterval: (summaryQuery) =>
      shouldPollActivityExtraction(summaryQuery.state.data) ? 2500 : false,
  });
  const accountsQuery = useQuery({
    queryKey: ["wechat-accounts", "article-filter"],
    queryFn: () => listWechatAccounts({ offset: 0, limit: 100 }),
  });
  const snapshotArticles = () =>
    queryClient.getQueriesData<ApiList<Article>>({ queryKey: ["articles"] });
  const restoreArticles = (snapshots: ReturnType<typeof snapshotArticles>) => {
    snapshots.forEach(([key, data]) => queryClient.setQueryData(key, data));
  };
  const remove = useMutation({
    mutationFn: deleteArticle,
    onMutate: async (articleId) => {
      await queryClient.cancelQueries({ queryKey: ["articles"] });
      const snapshots = snapshotArticles();
      queryClient.setQueriesData<ApiList<Article>>(
        { queryKey: ["articles"] },
        (data) => removeIdsFromApiList(data, [articleId])
      );
      setSelected((current) => (current?.id === articleId ? null : current));
      setSelectedRowKeys((keys) => keys.filter((key) => String(key) !== articleId));
      return { snapshots };
    },
    onSuccess: () => message.success("文章已删除"),
    onError: (error, _articleId, context) => {
      if (context) restoreArticles(context.snapshots);
      message.error(error instanceof Error ? error.message : "删除文章失败");
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["articles"] }),
  });
  const batchRemove = useMutation({
    mutationFn: deleteArticlesBatch,
    onMutate: async (articleIds) => {
      await queryClient.cancelQueries({ queryKey: ["articles"] });
      const snapshots = snapshotArticles();
      queryClient.setQueriesData<ApiList<Article>>(
        { queryKey: ["articles"] },
        (data) => removeIdsFromApiList(data, articleIds)
      );
      setSelected((current) =>
        current && articleIds.includes(current.id) ? null : current
      );
      setSelectedRowKeys((keys) =>
        keys.filter((key) => !articleIds.includes(String(key)))
      );
      return { snapshots };
    },
    onSuccess: (data: any) => {
      message.success(`批量删除完成${data?.deleted_count ? `，成功 ${data.deleted_count} 篇` : ""}`);
    },
    onError: (error, _articleIds, context) => {
      if (context) restoreArticles(context.snapshots);
      message.error(error instanceof Error ? error.message : "批量删除文章失败");
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["articles"] }),
  });
  const cleanAction = useMutation({
    mutationFn: (type: "orphan" | "duplicate" | "expired") => {
      if (type === "duplicate") return cleanDuplicateArticles();
      if (type === "expired") return cleanExpiredArticles();
      return cleanArticles();
    },
    onMutate: () => {
      message.loading({
        key: articleCleanupMessageKey,
        content: "正在清理文章…",
        duration: 0,
      });
    },
    onSuccess: (data: any) => {
      message.success({
        key: articleCleanupMessageKey,
        content: data?.message || "清理完成",
      });
    },
    onError: (error) => {
      message.error({
        key: articleCleanupMessageKey,
        content: error instanceof Error ? error.message : "清理文章失败",
      });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["articles"] }),
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
  const batchExtractActivities = useMutation({
    mutationFn: extractPendingActivities,
    onSuccess: (data) => {
      setWatchingBatchExtraction(true);
      message.success(
        `已加入 ${data.queued_count} 篇，跳过 ${data.skipped_count} 篇`
      );
    },
    onError: (error) =>
      message.error(
        error instanceof Error ? error.message : "批量活动抽取入队失败"
      ),
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["activity-extraction-summary"],
      });
      queryClient.invalidateQueries({ queryKey: ["articles"] });
    },
  });

  useEffect(() => {
    if (!activeExtractionRuns.length) return;

    const timer = window.setInterval(async () => {
      const finishedRunIds = new Set<string>();
      await Promise.all(
        activeExtractionRuns.map(async (item) => {
          try {
            const run: any = await getActivityExtractionRun(item.runId);
            if (["queued", "processing"].includes(run?.status)) return;

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
        queryClient.invalidateQueries({ queryKey: ["articles"] });
        queryClient.invalidateQueries({ queryKey: ["wechat-accounts"] });
      }
    }, 3000);

    return () => window.clearInterval(timer);
  }, [activeCollectionRuns, message, queryClient]);

  useEffect(() => {
    const summary = extractionSummaryQuery.data;
    if (!summary) return;
    if (shouldPollActivityExtraction(summary)) {
      queryClient.invalidateQueries({ queryKey: ["articles"] });
      return;
    }
    if (watchingBatchExtraction) {
      setWatchingBatchExtraction(false);
      message.success("批量抽取已完成");
      queryClient.invalidateQueries({ queryKey: ["activities"] });
    }
  }, [
    extractionSummaryQuery.data,
    message,
    queryClient,
    watchingBatchExtraction,
  ]);

  const confirmClean = (type: "orphan" | "duplicate" | "expired", title: string) => {
    modal.confirm({
      title,
      content: "该操作会直接删除匹配文章及关联图片映射，请确认后继续。",
      okText: "确认清理",
      okButtonProps: { danger: true },
      onOk: () => cleanAction.mutate(type),
    });
  };

  const confirmBatchExtraction = async () => {
    try {
      const refreshed = await extractionSummaryQuery.refetch();
      if (refreshed.error) throw refreshed.error;
      const pendingCount = refreshed.data?.pending_count || 0;
      if (!pendingCount) {
        message.info("暂无待抽取文章");
        return;
      }
      modal.confirm({
        title: "一键抽取",
        content: activityExtractionBatchConfirmation(pendingCount),
        okText: "开始抽取",
        cancelText: "取消",
        onOk: () => batchExtractActivities.mutateAsync(),
      });
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "获取待抽取文章数量失败"
      );
    }
  };

  const rowSelection: TableRowSelection<Article> = {
    selectedRowKeys,
    onChange: setSelectedRowKeys,
  };
  const activeExtractionArticleIds = useMemo(
    () => new Set(activeExtractionRuns.map((item) => item.articleId)),
    [activeExtractionRuns]
  );
  const articleDeletePending =
    remove.isPending || batchRemove.isPending || cleanAction.isPending;
  const renderExtractionStatus = (value?: string) => {
    const colorMap: Record<string, string> = {
      pending: "default",
      queued: "processing",
      processing: "processing",
      extracted: "success",
      not_activity: "default",
      failed: "error",
      fallback_required: "warning",
    };
    const status = value || "pending";
    return <Tag color={colorMap[status] || "default"}>{status}</Tag>;
  };

  const handleTableChange: TableProps<Article>["onChange"] = (
    pagination,
    filters,
    sorter
  ) => {
    const nextSorter = Array.isArray(sorter) ? sorter[0] : sorter;
    const nextSortBy =
      nextSorter.order &&
      (nextSorter.field === "publish_time" ||
        nextSorter.field === "activity_extraction_status")
        ? nextSorter.field
        : "publish_time";

    setPage(pagination.current || 1);
    setPageSize(pagination.pageSize || 20);
    setWechatAccountId(
      String(filters.wechat_account_id?.[0] || "") || undefined
    );
    setActivityExtractionStatus(
      String(filters.activity_extraction_status?.[0] || "") || undefined
    );
    setSortBy(nextSortBy);
    setSortOrder(nextSorter.order === "ascend" ? "asc" : "desc");
    setSelectedRowKeys([]);
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
    {
      title: "发布时间",
      dataIndex: "publish_time",
      width: 170,
      render: (value) => formatEpochSeconds(value),
    },
    {
      title: "公众号",
      key: "wechat_account_id",
      dataIndex: "mp_name",
      width: 190,
      ellipsis: true,
      filters: (accountsQuery.data?.list || []).map((account) => ({
        text: account.name || account.mp_name || account.id,
        value: account.id,
      })),
      filterSearch: true,
      filterMultiple: false,
      filteredValue: wechatAccountId ? [wechatAccountId] : null,
    },
    {
      title: "活动抽取",
      dataIndex: "activity_extraction_status",
      width: 120,
      render: renderExtractionStatus,
      filters: FILTERABLE_ACTIVITY_EXTRACTION_STATUSES.map((status) => ({
        text: status,
        value: status,
      })),
      filterMultiple: false,
      filteredValue: activityExtractionStatus
        ? [activityExtractionStatus]
        : null,
      sorter: true,
      sortOrder:
        sortBy === "activity_extraction_status"
          ? toAntSortOrder(sortOrder)
          : null,
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
            <Button
              danger
              type="text"
              icon={<DeleteOutlined />}
              disabled={articleDeletePending}
            />
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
          activeCollectionRuns.length > 0 ? (
            <Tag color="processing">采集中 {activeCollectionRuns.length}</Tag>
          ) : undefined
        }
      />
      <Card className="soft-card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            marginBottom: 12,
          }}
        >
          <Space wrap>
            <Popconfirm
              title={`删除选中的 ${selectedRowKeys.length} 篇文章？`}
              onConfirm={() => batchRemove.mutate(selectedRowKeys.map(String))}
              okButtonProps={{ danger: true }}
            >
              <Button
                danger
                icon={<DeleteOutlined />}
                disabled={!selectedRowKeys.length || articleDeletePending}
                loading={batchRemove.isPending}
              >
                批量删除
              </Button>
            </Popconfirm>
            <Button
              icon={<ClearOutlined />}
              loading={cleanAction.isPending}
              disabled={articleDeletePending}
              onClick={() => confirmClean("orphan", "清理无效文章？")}
            >
              清理无效
            </Button>
            <Button
              icon={<ClearOutlined />}
              loading={cleanAction.isPending}
              disabled={articleDeletePending}
              onClick={() => confirmClean("duplicate", "清理重复文章？")}
            >
              清理重复
            </Button>
            <Button
              icon={<ClearOutlined />}
              loading={cleanAction.isPending}
              disabled={articleDeletePending}
              onClick={() => confirmClean("expired", "清理 7 天前文章？")}
            >
              清理过期
            </Button>
          </Space>
          <Space wrap>
            <Button
              type="primary"
              icon={<RocketOutlined />}
              loading={batchExtractActivities.isPending}
              disabled={
                batchExtractActivities.isPending ||
                !extractionSummaryQuery.data?.pending_count
              }
              onClick={confirmBatchExtraction}
            >
              {activityExtractionBatchButtonText()}
            </Button>
          </Space>
        </div>
        <Table
          rowKey="id"
          rowSelection={rowSelection}
          loading={query.isLoading}
          columns={columns}
          dataSource={rows}
          onChange={handleTableChange}
          locale={{ emptyText: <EmptyState description="暂无文章" /> }}
          pagination={{
            current: page,
            pageSize,
            total: query.data?.total || 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 篇文章`,
            pageSizeOptions: [10, 20, 50, 100],
          }}
        />
      </Card>
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
