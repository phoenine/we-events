import {
  CalendarOutlined,
  ClearOutlined,
  DeleteOutlined,
  EnvironmentOutlined,
  EyeOutlined,
  LinkOutlined,
  ScheduleOutlined,
  TagsOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Card, Checkbox, DatePicker, Form, Input, Modal, Popconfirm, Select, Space, Tag, Tooltip, Typography } from "antd";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { useEffect, useMemo, useState } from "react";
import {
  deleteActivity,
  deleteEndedActivities,
  getActivityExtractionRun,
  getActivityImageEnrichmentContext,
  listActivities,
  previewActivityImageEnrichment,
  updateActivity,
} from "@/api/activities";
import EmptyState from "@/components/common/EmptyState";
import PageHeader from "@/components/common/PageHeader";
import { useAuthStore } from "@/store/authStore";
import type { Activity, ActivityImageEnrichmentPreview } from "@/types/api";
import {
  endedActivityCleanupConfirmation,
  endedActivityCleanupSuccess,
} from "@/utils/activityCleanup";
import {
  loadActivityExtractionRuns,
  removeActivityExtractionRuns,
} from "@/utils/activityExtractionRuns";
import { buildIcsEvent, downloadIcs } from "@/utils/calendar";
import {
  buildConfirmedEnrichmentUpdate,
  defaultSelectedSuggestionFields,
  ENRICHABLE_ACTIVITY_FIELDS,
  hasCriticalActivityGap,
  isActivityEnrichmentPreviewCurrent,
  type EnrichableActivityField,
} from "@/utils/activityImageEnrichment";
import { removeIdsFromList } from "@/utils/optimisticDelete";

const { TextArea } = Input;

const enrichmentFieldLabels: Record<EnrichableActivityField, string> = {
  event_time_text: "活动时间原文",
  start_at: "开始时间",
  end_at: "结束时间",
  location_text: "地点",
  registration_text: "报名说明",
  registration_method: "报名方式",
  registration_url: "报名链接",
  fee_text: "费用",
  audience: "目标人群",
};

interface CalendarFormValues {
  title: string;
  startsAt: Dayjs;
  endsAt?: Dayjs;
  location?: string;
  description?: string;
  url?: string;
  alarmMinutes?: number;
}

const eventStatusMeta: Record<string, { label: string; color: string; className: string; order: number }> = {
  ongoing: { label: "进行中", color: "green", className: "status-ongoing", order: 0 },
  upcoming: { label: "即将开始", color: "blue", className: "status-upcoming", order: 1 },
  unknown: { label: "时间待确认", color: "default", className: "status-unknown", order: 2 },
  ended: { label: "已结束", color: "default", className: "status-ended", order: 3 },
};

function getEventMeta(status?: string) {
  return eventStatusMeta[status || "unknown"] || eventStatusMeta.unknown;
}

function formatConfidence(value?: number) {
  if (typeof value !== "number") return undefined;
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(normalized)}%`;
}

function getActivityTime(activity: Activity) {
  if (activity.event_time_text) return activity.event_time_text;
  if (activity.start_at && activity.end_at) {
    return `${dayjs(activity.start_at).format("YYYY-MM-DD HH:mm")} - ${dayjs(activity.end_at).format("HH:mm")}`;
  }
  if (activity.start_at) return dayjs(activity.start_at).format("YYYY-MM-DD HH:mm");
  return "时间待确认";
}

function compareActivityTime(a?: string, b?: string) {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return dayjs(a).valueOf() - dayjs(b).valueOf();
}

function buildCalendarDescription(activity: Activity) {
  return [
    activity.summary,
    activity.event_time_text ? `活动时间：${activity.event_time_text}` : "",
    activity.fee_text ? `费用：${activity.fee_text}` : "",
    activity.audience ? `对象：${activity.audience}` : "",
    activity.registration_text ? `报名说明：${activity.registration_text}` : "",
    activity.registration_url ? `报名链接：${activity.registration_url}` : "",
    activity.article_url ? `原文链接：${activity.article_url}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function getDefaultCalendarRange(activity: Activity) {
  const startsAt = activity.start_at ? dayjs(activity.start_at) : undefined;
  const endsAt = activity.end_at ? dayjs(activity.end_at) : startsAt?.add(2, "hour");
  return { startsAt, endsAt };
}

export default function ActivitiesPage() {
  const currentUser = useAuthStore((state) => state.user);
  const [selected, setSelected] = useState<Activity | null>(null);
  const [calendarActivity, setCalendarActivity] = useState<Activity | null>(null);
  const [eventStatusFilter, setEventStatusFilter] = useState<string>("all");
  const [enrichmentPreview, setEnrichmentPreview] =
    useState<ActivityImageEnrichmentPreview | null>(null);
  const [selectedEnrichmentFields, setSelectedEnrichmentFields] = useState<
    EnrichableActivityField[]
  >([]);
  const [calendarForm] = Form.useForm<CalendarFormValues>();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const query = useQuery({
    queryKey: ["activities"],
    queryFn: () => listActivities({ limit: 200 }),
  });
  const remove = useMutation({
    mutationFn: deleteActivity,
    onMutate: async (activityId) => {
      await queryClient.cancelQueries({ queryKey: ["activities"] });
      const snapshots = queryClient.getQueriesData<Activity[]>({
        queryKey: ["activities"],
      });
      queryClient.setQueriesData<Activity[]>(
        { queryKey: ["activities"] },
        (data) => removeIdsFromList(data, [activityId])
      );
      setSelected((current) => (current?.id === activityId ? null : current));
      return { snapshots };
    },
    onSuccess: () => message.success("活动已删除"),
    onError: (error, _activityId, context) => {
      context?.snapshots.forEach(([key, data]) => queryClient.setQueryData(key, data));
      message.error(error instanceof Error ? error.message : "删除活动失败");
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["activities"] }),
  });
  const enrichmentContext = useQuery({
    queryKey: ["activity-image-enrichment-context", selected?.id],
    queryFn: () => getActivityImageEnrichmentContext(selected!.id),
    enabled: Boolean(selected && hasCriticalActivityGap(selected)),
  });
  const previewEnrichment = useMutation({
    mutationFn: (activityId: string) => previewActivityImageEnrichment(activityId),
    onSuccess: (preview) => {
      if (!isActivityEnrichmentPreviewCurrent(selected, preview)) {
        message.warning("活动已切换，请重新生成图片补充建议");
        return;
      }
      setEnrichmentPreview(preview);
      setSelectedEnrichmentFields(
        defaultSelectedSuggestionFields(preview.current, preview)
      );
    },
    onError: (error) => {
      const text = error instanceof Error ? error.message : "图片信息读取失败";
      if (text.includes("OCR") || text.includes("未配置") || text.includes("未启用")) {
        message.warning(text);
      } else {
        message.error(text);
      }
    },
  });
  const applyEnrichment = useMutation({
    mutationFn: async () => {
      const preview = enrichmentPreview;
      if (!preview || !isActivityEnrichmentPreviewCurrent(selected, preview)) {
        throw new Error("活动已切换，请重新生成图片补充建议");
      }
      const payload = buildConfirmedEnrichmentUpdate(
        preview.current,
        preview,
        selectedEnrichmentFields
      );
      const activityId = preview.activity_id;
      const updated = await updateActivity(activityId, payload);
      return { activityId, updated };
    },
    onSuccess: ({ activityId, updated }) => {
      if (selected?.id === activityId) setSelected(updated);
      setEnrichmentPreview(null);
      setSelectedEnrichmentFields([]);
      message.success("活动信息已补充");
      queryClient.invalidateQueries({ queryKey: ["activities"] });
      queryClient.invalidateQueries({
        queryKey: ["activity-image-enrichment-context", activityId],
      });
    },
    onError: (error) =>
      message.error(error instanceof Error ? error.message : "保存补充信息失败"),
  });

  const activities = useMemo(() => {
    return [...(query.data || [])]
      .filter((activity) =>
        eventStatusFilter === "all" ? true : activity.event_status === eventStatusFilter
      )
      .sort((a, b) => {
      const statusDiff = getEventMeta(a.event_status).order - getEventMeta(b.event_status).order;
      if (statusDiff !== 0) return statusDiff;
      if (a.event_status === "ended" || b.event_status === "ended") {
        return compareActivityTime(b.start_at, a.start_at);
      }
      return compareActivityTime(a.start_at, b.start_at);
    });
  }, [eventStatusFilter, query.data]);
  const activityStats = useMemo(() => {
    const total = activities.length;
    const upcoming = activities.filter((item) => item.event_status === "upcoming").length;
    const ongoing = activities.filter((item) => item.event_status === "ongoing").length;
    const needsReview = activities.filter((item) => item.review_status === "needs_review").length;
    return [
      { label: "总活动", description: "当前已抽取活动", value: total, tone: "blue" },
      { label: "进行中", description: "正在发生的活动", value: ongoing, tone: "green" },
      { label: "即将开始", description: "按时间排序靠前", value: upcoming, tone: "purple" },
      { label: "需复核", description: "待人工确认字段", value: needsReview, tone: "amber" },
    ];
  }, [activities]);
  const cleanEnded = useMutation({
    mutationFn: deleteEndedActivities,
    onSuccess: (data) => {
      setSelected((current) =>
        current?.event_status === "ended" ? null : current
      );
      message.success(endedActivityCleanupSuccess(data.deleted_count));
    },
    onError: (error) =>
      message.error(
        error instanceof Error ? error.message : "清理已结束活动失败"
      ),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["activities"] }),
  });

  useEffect(() => {
    const timer = window.setInterval(async () => {
      const runs = loadActivityExtractionRuns();
      if (!runs.length) return;

      const finishedRunIds = new Set<string>();
      await Promise.all(
        runs.map(async (item) => {
          try {
            const run: any = await getActivityExtractionRun(item.runId);
            if (!["queued", "processing"].includes(run?.status)) {
              finishedRunIds.add(item.runId);
            }
          } catch {
            finishedRunIds.add(item.runId);
          }
        })
      );

      if (finishedRunIds.size) {
        removeActivityExtractionRuns(finishedRunIds);
        queryClient.invalidateQueries({ queryKey: ["activities"] });
      }
    }, 2500);

    return () => window.clearInterval(timer);
  }, [queryClient]);

  const openCalendarModal = (activity: Activity) => {
    const { startsAt, endsAt } = getDefaultCalendarRange(activity);
    setCalendarActivity(activity);
    calendarForm.setFieldsValue({
      title: activity.title || "未命名活动",
      startsAt,
      endsAt,
      location: activity.location_text || "",
      description: buildCalendarDescription(activity),
      url: activity.registration_url || activity.article_url || "",
      alarmMinutes: 60,
    });
  };

  const submitCalendarEvent = async () => {
    const values = await calendarForm.validateFields();
    const content = buildIcsEvent({
      title: values.title,
      startsAt: values.startsAt.toISOString(),
      endsAt: values.endsAt?.toISOString(),
      location: values.location,
      description: values.description,
      url: values.url,
      alarmMinutes: values.alarmMinutes,
    });
    downloadIcs(values.title, content);
    message.success("已生成日历文件");
    setCalendarActivity(null);
  };

  return (
    <div className="page">
      <PageHeader
        title="活动"
        subtitle="从文章中抽取的活动信息，支持浏览、复核和清理。"
        actions={
          <>
            <Select
              className="status-filter"
              value={eventStatusFilter}
              onChange={setEventStatusFilter}
              options={[
                { value: "all", label: "全部状态" },
                { value: "ongoing", label: "进行中" },
                { value: "upcoming", label: "即将开始" },
                { value: "unknown", label: "时间待确认" },
                { value: "ended", label: "已结束" },
              ]}
            />
            <Popconfirm
              title={endedActivityCleanupConfirmation()}
              okText="确认清理"
              okButtonProps={{ danger: true }}
              onConfirm={() => cleanEnded.mutate()}
            >
              <Button
                danger
                icon={<ClearOutlined />}
                loading={cleanEnded.isPending}
                disabled={cleanEnded.isPending}
              >
                清理过期
              </Button>
            </Popconfirm>
          </>
        }
      />

      <div className="wechat-stats">
        {activityStats.map((item) => (
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
        className="soft-card content-panel activity-list-panel"
        title="活动列表"
        extra={<span className="panel-count">共 {activities.length} 个活动</span>}
      >
        {query.isLoading ? (
          <div className="activity-grid">
            {Array.from({ length: 6 }).map((_, index) => (
              <Card key={index} loading className="activity-card" />
            ))}
          </div>
        ) : activities.length ? (
          <div className="activity-grid">
            {activities.map((activity) => {
              const eventMeta = getEventMeta(activity.event_status);
              const confidenceText = formatConfidence(activity.confidence);
              const lowConfidence = typeof activity.confidence === "number" && activity.confidence < 0.5;
              const activityTitle = activity.title || "未命名活动";
              const activitySummary = activity.summary || activity.registration_text || "暂无活动摘要";
              const activityTime = getActivityTime(activity);
              const activityLocation = activity.location_text || "地点待确认";
              const activityFee = activity.fee_text || "费用待确认";
              const activityAudience = activity.audience || "人群待确认";

              return (
                <Card
                  key={activity.id}
                  className={`activity-card ${eventMeta.className}`}
                  hoverable
                  onClick={() => setSelected(activity)}
                >
                  <div className="activity-card-head">
                    <Space size={6} wrap>
                      <Tag color={eventMeta.color}>{eventMeta.label}</Tag>
                    </Space>
                    {confidenceText && (
                      <Tag color={lowConfidence ? "warning" : "default"}>
                        置信度 {confidenceText}
                      </Tag>
                    )}
                  </div>

                  <Tooltip title={activityTitle}>
                    <Typography.Title level={4} className="activity-card-title">
                      {activityTitle}
                    </Typography.Title>
                  </Tooltip>

                  <div className="activity-title-divider" />

                  <Tooltip title={activitySummary}>
                    <Typography.Paragraph className="activity-summary" ellipsis={{ rows: 2 }}>
                      {activitySummary}
                    </Typography.Paragraph>
                  </Tooltip>

                  <div className="activity-meta">
                    <Tooltip title={activityTime}>
                      <div>
                        <CalendarOutlined />
                        <span>{activityTime}</span>
                      </div>
                    </Tooltip>
                    <Tooltip title={activityLocation}>
                      <div>
                        <EnvironmentOutlined />
                        <span>{activityLocation}</span>
                      </div>
                    </Tooltip>
                  </div>

                  <div className="activity-info-list">
                    <Tooltip title={activityFee}>
                      <div>
                        <TagsOutlined />
                        <span>{activityFee}</span>
                      </div>
                    </Tooltip>
                    <Tooltip title={activityAudience}>
                      <div>
                        <TeamOutlined />
                        <span>{activityAudience}</span>
                      </div>
                    </Tooltip>
                  </div>

                  <div className="activity-card-footer" onClick={(event) => event.stopPropagation()}>
                    <Button type="link" size="small" icon={<ScheduleOutlined />} onClick={() => openCalendarModal(activity)}>
                      日历
                    </Button>
                    <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => setSelected(activity)}>
                      查看详情
                    </Button>
                    {activity.article_url && (
                      <Button type="link" size="small" icon={<LinkOutlined />} href={activity.article_url} target="_blank">
                        原文
                      </Button>
                    )}
                    <Popconfirm title="删除这个活动？" onConfirm={() => remove.mutate(activity.id)}>
                      <Button
                        danger
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        disabled={remove.isPending}
                      />
                    </Popconfirm>
                  </div>
                </Card>
              );
            })}
          </div>
        ) : (
          <EmptyState description="暂无活动" />
        )}
      </Card>

      <Modal
        title={selected?.title || "活动详情"}
        centered
        open={!!selected}
        footer={null}
        onCancel={() => {
          setSelected(null);
          setEnrichmentPreview(null);
          setSelectedEnrichmentFields([]);
        }}
        width={680}
        className="activity-detail-modal"
      >
        <div className="activity-detail">
          <div className="activity-detail-tags">
            <Space wrap size={[6, 6]}>
              <Tag color={getEventMeta(selected?.event_status).color}>{getEventMeta(selected?.event_status).label}</Tag>
              {typeof selected?.confidence === "number" && (
                <Tag>置信度 {formatConfidence(selected.confidence)}</Tag>
              )}
            </Space>
          </div>
          <div className="activity-detail-summary">{selected?.summary || "暂无活动摘要"}</div>
          <div className="activity-detail-grid">
            {[
              ["地点", selected?.location_text || "-"],
              ["时间", selected ? getActivityTime(selected) : "-"],
              ["费用", selected?.fee_text || "-"],
              ["对象", selected?.audience || "-"],
              ["报名方式", selected?.registration_method || "-"],
              ["报名说明", selected?.registration_text || "-"],
            ].map(([label, value]) => (
              <div className="activity-detail-item" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <div className="activity-detail-links">
            {selected?.registration_url && (
              <Typography.Link href={selected.registration_url} target="_blank">
                报名链接
              </Typography.Link>
            )}
            {selected?.article_url && (
              <Typography.Link href={selected.article_url} target="_blank">
                原文链接
              </Typography.Link>
            )}
          </div>
          {!!selected?.warnings?.length && (
            <div className="activity-detail-warning">
              <Typography.Text strong>提示</Typography.Text>
              <div className="activity-warning-list">
                {selected.warnings.map((warning, index) => (
                  <Tag key={`${warning}-${index}`} color="warning">
                    {warning}
                  </Tag>
                ))}
              </div>
            </div>
          )}
          <div className="activity-detail-actions">
            {selected && (
              <Space wrap>
                <Button icon={<ScheduleOutlined />} onClick={() => openCalendarModal(selected)}>
                  添加到日历
                </Button>
                {currentUser?.role === "admin" &&
                  hasCriticalActivityGap(selected) &&
                  enrichmentContext.data?.ocr_enabled &&
                  enrichmentContext.data.image_count > 0 && (
                    <Button
                      loading={previewEnrichment.isPending}
                      onClick={() => previewEnrichment.mutate(selected.id)}
                    >
                      从图片补充
                    </Button>
                  )}
              </Space>
            )}
            <Popconfirm title="删除这个活动？" onConfirm={() => selected && remove.mutate(selected.id)}>
              <Button
                danger
                icon={<DeleteOutlined />}
                loading={remove.isPending}
                disabled={remove.isPending}
              >
                删除活动
              </Button>
            </Popconfirm>
          </div>
        </div>
      </Modal>

      <Modal
        title="从图片补充活动信息"
        open={isActivityEnrichmentPreviewCurrent(selected, enrichmentPreview)}
        okText="确认更新"
        cancelText="取消"
        confirmLoading={applyEnrichment.isPending}
        okButtonProps={{ disabled: !selectedEnrichmentFields.length }}
        onCancel={() => {
          setEnrichmentPreview(null);
          setSelectedEnrichmentFields([]);
        }}
        onOk={() => applyEnrichment.mutate()}
        width={760}
      >
        {enrichmentPreview && (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Typography.Text type="secondary">
              已读取 {enrichmentPreview.images.length} 张文章图片。请选择需要写入的建议字段；已有值默认不会覆盖。
            </Typography.Text>
            <Checkbox.Group
              value={selectedEnrichmentFields}
              onChange={(values) =>
                setSelectedEnrichmentFields(values as EnrichableActivityField[])
              }
              style={{ width: "100%" }}
            >
              <Space direction="vertical" style={{ width: "100%" }}>
                {ENRICHABLE_ACTIVITY_FIELDS.filter(
                  (field) => enrichmentPreview.suggestions[field] !== undefined
                ).map((field) => (
                  <Card key={field} size="small">
                    <Checkbox value={field}>{enrichmentFieldLabels[field]}</Checkbox>
                    <div style={{ marginTop: 8 }}>
                      <Typography.Text type="secondary">当前：</Typography.Text>{" "}
                      <Typography.Text>
                        {String(enrichmentPreview.current[field] || "-")}
                      </Typography.Text>
                    </div>
                    <div>
                      <Typography.Text type="secondary">建议：</Typography.Text>{" "}
                      <Typography.Text strong>
                        {String(enrichmentPreview.suggestions[field] || "-")}
                      </Typography.Text>
                    </div>
                  </Card>
                ))}
              </Space>
            </Checkbox.Group>
            {!!enrichmentPreview.evidence.length && (
              <Card size="small" title="识别证据">
                <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>
                  {JSON.stringify(enrichmentPreview.evidence, null, 2)}
                </pre>
              </Card>
            )}
            {!!enrichmentPreview.warnings.length && (
              <Alert
                type="warning"
                showIcon
                message="部分图片或字段需要人工确认"
                description={enrichmentPreview.warnings.join("；")}
              />
            )}
          </Space>
        )}
      </Modal>

      <Modal
        title="添加到日历"
        className="calendar-modal activity-calendar-modal"
        centered
        open={!!calendarActivity}
        okText="生成日历文件"
        cancelText="取消"
        onCancel={() => setCalendarActivity(null)}
        onOk={submitCalendarEvent}
        width={640}
      >
        <Form form={calendarForm} layout="vertical">
          <Form.Item name="title" label="事件标题" rules={[{ required: true, message: "请输入事件标题" }]}>
            <Input />
          </Form.Item>
          <div className="calendar-form-grid">
            <Form.Item name="startsAt" label="开始时间" rules={[{ required: true, message: "请选择开始时间" }]}>
              <DatePicker showTime format="YYYY-MM-DD HH:mm" style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item
              name="endsAt"
              label="结束时间"
              dependencies={["startsAt"]}
              rules={[
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    const startsAt = getFieldValue("startsAt");
                    if (!value || !startsAt || value.isAfter(startsAt)) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error("结束时间必须晚于开始时间"));
                  },
                }),
              ]}
            >
              <DatePicker showTime format="YYYY-MM-DD HH:mm" style={{ width: "100%" }} />
            </Form.Item>
          </div>
          <Form.Item name="location" label="地点">
            <Input />
          </Form.Item>
          <Form.Item name="url" label="链接">
            <Input />
          </Form.Item>
          <Form.Item name="alarmMinutes" label="提醒">
            <Select
              options={[
                { value: 0, label: "不提醒" },
                { value: 15, label: "提前 15 分钟" },
                { value: 60, label: "提前 1 小时" },
                { value: 1440, label: "提前 1 天" },
              ]}
            />
          </Form.Item>
          <Form.Item name="description" label="备注">
            <TextArea rows={6} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
