import { SearchOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { App, Avatar, Button, Card, Form, Input, List, Space, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createWechatAccount,
  getWechatAccountByArticle,
  searchWechatAccounts,
} from "@/api/wechatAccounts";
import PageHeader from "@/components/common/PageHeader";

function normalizeLookupResult(data: any) {
  const article = data?.wechat_account || data;
  const mpInfo = article?.mp_info || {};
  return {
    name: mpInfo?.mp_name || article?.mp_name || article?.name || "",
    sourceId:
      mpInfo?.biz ||
      article?.wechat_account_id ||
      article?.faker_id ||
      article?.id ||
      "",
    logoUrl: mpInfo?.logo || article?.logo_url || article?.avatar || "",
    description: mpInfo?.signature || article?.mp_intro || article?.account_description || "",
  };
}

function normalizeSearchName(item: any) {
  const name = item?.nickname || item?.mp_name || item?.name || "";
  const text = String(name);
  return text.includes("...") || text.includes("…") ? "" : name;
}

export default function AddWechatAccountPage() {
  const [form] = Form.useForm();
  const [preview, setPreview] = useState<any>(null);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const { message } = App.useApp();
  const navigate = useNavigate();
  const lookup = useMutation({
    mutationFn: getWechatAccountByArticle,
    onSuccess: (data: any) => {
      const account = normalizeLookupResult(data);
      setPreview(account);
      form.setFieldsValue({
        wechatAccountName: account.name,
        wechatAccountSourceId: account.sourceId,
        logoUrl: account.logoUrl,
        description: account.description,
      });
      message.success("已读取公众号信息");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "读取失败"),
  });
  const create = useMutation({
    mutationFn: createWechatAccount,
    onSuccess: () => {
      message.success("公众号已保存");
      navigate("/wechat-accounts");
    },
  });
  const keywordSearch = useMutation({
    mutationFn: (kw: string) => searchWechatAccounts(kw),
    onSuccess: (data: any) => setSearchResults(data?.list || []),
    onError: (error) => message.error(error instanceof Error ? error.message : "搜索失败"),
  });

  const selectSearchResult = (item: any) => {
    const account = {
      name: normalizeSearchName(item),
      sourceId: item?.fakeid || item?.faker_id || item?.wechat_account_id || item?.id || "",
      logoUrl: item?.round_head_img || item?.logo_url || item?.avatar || "",
      description: item?.signature || item?.description || "",
    };
    setPreview(account);
    form.setFieldsValue({
      wechatAccountName: account.name,
      wechatAccountSourceId: account.sourceId,
      logoUrl: account.logoUrl,
      description: account.description,
    });
    if (!account.name) {
      message.warning("搜索结果名称被微信截断，请手动补全公众号名称后保存。");
    }
  };

  return (
    <div className="page">
      <PageHeader title="添加公众号" subtitle="通过公众号文章链接读取账号信息并保存。" />
      <Card className="soft-card">
        <Form form={form} layout="vertical" onFinish={(values) => create.mutate(values)}>
          <Form.Item label="文章链接" name="article_url">
            <Input.Search
              placeholder="https://mp.weixin.qq.com/s/..."
              enterButton={<Button icon={<SearchOutlined />}>读取</Button>}
              loading={lookup.isPending}
              onSearch={(value) => value && lookup.mutate(value)}
            />
          </Form.Item>
          <Form.Item label="关键词搜索公众号">
            <Input.Search
              placeholder="输入公众号名称"
              enterButton={<Button icon={<SearchOutlined />}>搜索</Button>}
              loading={keywordSearch.isPending}
              onSearch={(value) => value && keywordSearch.mutate(value)}
            />
          </Form.Item>
          {!!searchResults.length && (
            <List
              style={{ marginBottom: 16 }}
              bordered
              dataSource={searchResults}
              renderItem={(item: any) => (
                <List.Item
                  actions={[
                    <Button key="select" type="link" onClick={() => selectSearchResult(item)}>
                      选择
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={<Avatar src={item.round_head_img || item.logo_url} />}
                    title={item.nickname || item.mp_name || item.name}
                    description={item.signature || item.description || item.fakeid}
                  />
                </List.Item>
              )}
            />
          )}
          {preview && (
            <Space style={{ marginBottom: 16 }}>
              <Avatar src={preview.logoUrl}>{preview.name?.slice(0, 1)}</Avatar>
              <Typography.Text>{preview.name}</Typography.Text>
            </Space>
          )}
          <Form.Item name="wechatAccountName" label="公众号名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="wechatAccountSourceId" label="公众号标识" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="logoUrl" label="Logo URL">
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={create.isPending}>
            保存公众号
          </Button>
        </Form>
      </Card>
    </div>
  );
}
