import {
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Avatar, Button, Card, Input, Pagination, Popconfirm, Space, Tag, Tooltip } from "antd";
import dayjs from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteWechatAccount,
  getArticleCollectionRun,
  listWechatAccounts,
  syncWechatAccountArticles,
} from "@/api/wechatAccounts";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import type { ApiList, WechatAccount } from "@/types/api";
import {
  addArticleCollectionRun,
  loadArticleCollectionRuns,
  removeArticleCollectionRuns,
} from "@/utils/articleCollectionRuns";
import { removeIdsFromApiList } from "@/utils/optimisticDelete";

const avatarColors = ["#3B82F6", "#0891B2", "#16A34A", "#F59E0B", "#635BFF", "#E11D48"];

function getAccountName(account: WechatAccount) {
  return account.name || account.mp_name || account.id;
}

function getAccountInitial(account: WechatAccount) {
  return getAccountName(account).trim().slice(0, 1).toUpperCase() || "?";
}

function getAccountLastFetch(account: WechatAccount) {
  const value = account.last_fetch || account.sync_time || account.update_time;
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "尚未采集";
}

export default function WechatAccountsPage() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [kw, setKw] = useState("");
  const [activeCollectionRuns, setActiveCollectionRuns] = useState(loadArticleCollectionRuns);
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const query = useQuery({
    queryKey: ["wechat-accounts", page, pageSize, kw],
    queryFn: () =>
      listWechatAccounts({ offset: (page - 1) * pageSize, limit: pageSize, kw }),
  });
  const sync = useMutation({
    mutationFn: (id: string) => syncWechatAccountArticles(id),
    onSuccess: (data: any) => {
      if (data?.run_id) {
        addArticleCollectionRun({ runId: data.run_id });
        setActiveCollectionRuns((runs) => {
          if (runs.some((item) => item.runId === data.run_id)) return runs;
          return [...runs, { runId: data.run_id }];
        });
      }
      if (data?.status === "skipped") {
        message.info("当前公众号暂不可采集");
      } else {
        message.success(data?.already_running ? "采集任务已在队列中" : "已加入采集队列");
      }
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "触发采集失败"),
  });
  const remove = useMutation({
    mutationFn: deleteWechatAccount,
    onMutate: async (accountId) => {
      await queryClient.cancelQueries({ queryKey: ["wechat-accounts"] });
      const snapshots = queryClient.getQueriesData<ApiList<WechatAccount>>({
        queryKey: ["wechat-accounts"],
      });
      queryClient.setQueriesData<ApiList<WechatAccount>>(
        { queryKey: ["wechat-accounts"] },
        (data) => removeIdsFromApiList(data, [accountId])
      );
      return { snapshots };
    },
    onSuccess: () => message.success("公众号已删除"),
    onError: (error, _accountId, context) => {
      context?.snapshots.forEach(([key, data]) => queryClient.setQueryData(key, data));
      message.error(error instanceof Error ? error.message : "删除公众号失败");
    },
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["wechat-accounts"] }),
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
        queryClient.invalidateQueries({ queryKey: ["wechat-accounts"] });
        queryClient.invalidateQueries({ queryKey: ["articles"] });
      }
    }, 3000);

    return () => window.clearInterval(timer);
  }, [activeCollectionRuns, message, queryClient]);

  const activeCollectionRunCount = useMemo(
    () => activeCollectionRuns.length,
    [activeCollectionRuns]
  );

  const rows = query.data?.list || [];
  const enabledCount = rows.filter((row) => row.status !== 0).length;

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
            <Button
              icon={<ReloadOutlined />}
              loading={query.isFetching}
              onClick={() => query.refetch()}
            >
              刷新
            </Button>
            {activeCollectionRunCount > 0 && <Tag color="processing">采集中 {activeCollectionRunCount}</Tag>}
            <Link to="/wechat-accounts/add">
              <Button type="primary" icon={<PlusOutlined />}>
                添加公众号
              </Button>
            </Link>
          </>
        }
      />
      <div className="wechat-stats">
        {[
          { label: "已接入", description: "可用于文章采集的来源", value: query.data?.total || rows.length, tone: "green" },
          { label: "启用中", description: "当前启用的公众号", value: enabledCount, tone: "blue" },
          { label: "采集中", description: "正在执行的采集任务", value: activeCollectionRunCount, tone: "amber" },
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
        title="公众号列表"
        extra={<span className="panel-count">共 {query.data?.total || 0} 个公众号</span>}
        loading={query.isLoading}
      >
        {rows.length ? (
          <>
            <div className="source-card-grid">
              {rows.map((account, index) => (
                <Card key={account.id} className="source-card" hoverable>
                  <div className="source-card-main">
                    <Avatar
                      className="source-avatar"
                      src={account.logo_url || account.mp_cover}
                      style={{ backgroundColor: avatarColors[index % avatarColors.length] }}
                    >
                      {getAccountInitial(account)}
                    </Avatar>
                    <div className="source-text">
                      <div className="source-name">{getAccountName(account)}</div>
                      <div className="source-id">{account.faker_id || account.id}</div>
                    </div>
                  </div>

                  <div className="source-card-bottom">
                    <div className="source-last-fetch">最近采集 {getAccountLastFetch(account)}</div>
                    <Space size={8}>
                      <Tooltip title="采集">
                        <Button
                          className="source-icon-button"
                          icon={<SyncOutlined />}
                          loading={sync.isPending}
                          onClick={() => sync.mutate(account.id)}
                        />
                      </Tooltip>
                      <Tooltip title="复制公众号标识">
                        <Button
                          className="source-icon-button"
                          icon={<CopyOutlined />}
                          onClick={() => {
                            navigator.clipboard.writeText(account.faker_id || account.id);
                            message.success("已复制");
                          }}
                        />
                      </Tooltip>
                      <Popconfirm title="删除这个公众号？" onConfirm={() => remove.mutate(account.id)}>
                        <Button
                          danger
                          className="source-icon-button"
                          icon={<DeleteOutlined />}
                          disabled={remove.isPending}
                        />
                      </Popconfirm>
                    </Space>
                  </div>
                </Card>
              ))}
            </div>
            <div className="source-pagination">
              <Pagination
                current={page}
                pageSize={pageSize}
                total={query.data?.total || 0}
                showSizeChanger
                showTotal={(total) => `共 ${total} 个公众号`}
                pageSizeOptions={[10, 20, 50, 100]}
                onChange={(nextPage, nextPageSize) => {
                  setPage(nextPage);
                  setPageSize(nextPageSize);
                }}
              />
            </div>
          </>
        ) : (
          <EmptyState description="暂无公众号" />
        )}
      </Card>
    </div>
  );
}
