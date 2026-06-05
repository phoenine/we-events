import { SaveOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Typography,
} from "antd";
import { useEffect, useMemo } from "react";
import { createConfig, listConfigs, updateConfig } from "@/api/configs";
import PageHeader from "@/components/common/PageHeader";
import type { ConfigItem } from "@/types/api";

type ConfigFieldType = "number" | "boolean" | "string";

interface ConfigField {
  key: string;
  type: ConfigFieldType;
  description: string;
}

interface ConfigValues {
  max_page?: number;
  sync_interval?: number;
  interval?: number;
  activity_auto_extract?: boolean;
  activity_use_images?: boolean;
  activity_low_confidence_policy?: string;
  llm_enabled?: boolean;
  llm_api_base?: string;
  llm_model?: string;
  llm_max_tokens?: number;
  llm_temperature?: number;
  llm_use_for_extraction?: boolean;
  llm_use_for_fallback?: boolean;
  llm_use_for_image?: boolean;
  llm_retry_count?: number;
}

const CONFIG_FIELDS: ConfigField[] = [
  { key: "max_page", type: "number", description: "单次采集页数上限" },
  { key: "sync_interval", type: "number", description: "同步冷却时间（秒）" },
  { key: "interval", type: "number", description: "请求间隔（秒）" },
  { key: "activity.auto_extract", type: "boolean", description: "采集后自动抽取活动" },
  { key: "activity.use_images", type: "boolean", description: "活动抽取读取图片信息" },
  {
    key: "activity.low_confidence_policy",
    type: "string",
    description: "低置信度处理策略",
  },
  { key: "llm.enabled", type: "boolean", description: "启用 LLM" },
  { key: "llm.api_base", type: "string", description: "LLM API Base URL" },
  { key: "llm.model", type: "string", description: "LLM 模型" },
  { key: "llm.max_tokens", type: "number", description: "单次抽取 token 上限" },
  { key: "llm.temperature", type: "number", description: "LLM 温度" },
  { key: "llm.use_for_extraction", type: "boolean", description: "用于活动抽取" },
  { key: "llm.use_for_fallback", type: "boolean", description: "用于正文采集兜底" },
  { key: "llm.use_for_image", type: "boolean", description: "用于图片信息理解" },
  { key: "llm.retry_count", type: "number", description: "失败重试次数" },
];

const DEFAULT_VALUES: Required<ConfigValues> = {
  max_page: 5,
  sync_interval: 60,
  interval: 10,
  activity_auto_extract: true,
  activity_use_images: true,
  activity_low_confidence_policy: "review",
  llm_enabled: false,
  llm_api_base: "https://api.siliconflow.cn/v1/chat/completions",
  llm_model: "Qwen/Qwen3-32B",
  llm_max_tokens: 4096,
  llm_temperature: 0.2,
  llm_use_for_extraction: true,
  llm_use_for_fallback: true,
  llm_use_for_image: true,
  llm_retry_count: 1,
};

function formName(configKey: string) {
  return configKey.replaceAll(".", "_") as keyof ConfigValues;
}

function parseValue(value: unknown, type: ConfigFieldType) {
  if (type === "boolean") {
    if (typeof value === "boolean") return value;
    return String(value ?? "").trim().toLowerCase() in ["1", "true", "yes", "on"];
  }
  if (type === "number") {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : undefined;
  }
  return String(value ?? "");
}

function serializeValue(value: unknown, type: ConfigFieldType) {
  if (type === "boolean") return value ? "true" : "false";
  if (type === "number") return String(value ?? 0);
  return String(value ?? "");
}

function buildInitialValues(configs: ConfigItem[]) {
  const byKey = new Map(configs.map((item) => [item.key, item]));
  const values: ConfigValues = { ...DEFAULT_VALUES };
  for (const field of CONFIG_FIELDS) {
    const name = formName(field.key);
    const item = byKey.get(field.key);
    if (!item) continue;
    values[name] = parseValue(item.value, field.type) as never;
  }
  return values;
}

export default function ConfigsPage() {
  const [form] = Form.useForm<ConfigValues>();
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  const query = useQuery({
    queryKey: ["configs"],
    queryFn: () => listConfigs({ limit: 100 }),
  });

  const existingKeys = useMemo(
    () => new Set((query.data?.list || []).map((item) => item.key)),
    [query.data?.list]
  );

  useEffect(() => {
    form.setFieldsValue(buildInitialValues(query.data?.list || []));
  }, [form, query.data?.list]);

  const save = useMutation({
    mutationFn: async (values: ConfigValues) => {
      const tasks = CONFIG_FIELDS.map((field) => {
        const name = formName(field.key);
        const payload = {
          key: field.key,
          value: serializeValue(values[name], field.type),
          description: field.description,
        };
        return existingKeys.has(field.key)
          ? updateConfig(field.key, payload)
          : createConfig(payload);
      });
      await Promise.all(tasks);
    },
    onSuccess: () => {
      message.success("配置已保存");
      queryClient.invalidateQueries({ queryKey: ["configs"] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存失败"),
  });

  return (
    <div className="page">
      <PageHeader
        title="配置"
        subtitle="管理采集节奏、活动抽取与 LLM 运行配置。"
        actions={
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={save.isPending}
            onClick={() => form.submit()}
          >
            保存配置
          </Button>
        }
      />
      <Form
        form={form}
        layout="vertical"
        initialValues={DEFAULT_VALUES}
        onFinish={(values) => save.mutate(values)}
      >
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Card className="soft-card" title="采集节奏">
            <div className="settings-grid">
              <Form.Item name="max_page" label="单次采集页数上限">
                <InputNumber min={1} max={50} precision={0} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="sync_interval" label="同步冷却时间（秒）">
                <InputNumber min={0} precision={0} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="interval" label="请求间隔（秒）">
                <InputNumber min={0} precision={0} style={{ width: "100%" }} />
              </Form.Item>
            </div>
          </Card>

          <Card className="soft-card" title="活动抽取">
            <div className="settings-grid">
              <Form.Item
                name="activity_auto_extract"
                label="采集后自动抽取活动"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item
                name="activity_use_images"
                label="读取图片信息"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item name="activity_low_confidence_policy" label="低置信度处理">
                <Select
                  options={[
                    { value: "review", label: "待确认" },
                    { value: "draft", label: "保留草稿" },
                    { value: "discard", label: "丢弃" },
                  ]}
                />
              </Form.Item>
            </div>
          </Card>

          <Card className="soft-card" title="LLM">
            <div className="settings-grid">
              <Form.Item name="llm_enabled" label="启用 LLM" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item label="API Key">
                <Input disabled value="由后端环境变量 LLM_API_KEY 管理" />
              </Form.Item>
              <Form.Item name="llm_api_base" label="API Base URL">
                <Input />
              </Form.Item>
              <Form.Item name="llm_model" label="模型">
                <Input />
              </Form.Item>
              <Form.Item name="llm_max_tokens" label="Token 上限">
                <InputNumber min={512} max={128000} precision={0} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="llm_temperature" label="温度">
                <InputNumber min={0} max={2} step={0.1} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="llm_retry_count" label="失败重试次数">
                <InputNumber min={0} max={5} precision={0} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item
                name="llm_use_for_extraction"
                label="用于活动抽取"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item
                name="llm_use_for_fallback"
                label="用于正文兜底"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item
                name="llm_use_for_image"
                label="用于图片理解"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
            </div>
            <Typography.Text type="secondary">
              API Key 不写入运行时配置表，后端通过环境变量读取。
            </Typography.Text>
          </Card>
        </Space>
      </Form>
    </div>
  );
}
