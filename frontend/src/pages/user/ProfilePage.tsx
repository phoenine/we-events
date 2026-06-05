import { useMutation, useQuery } from "@tanstack/react-query";
import { App, Button, Card, Form, Input, Switch } from "antd";
import { useEffect } from "react";
import { getCurrentUser, updateUser } from "@/api/user";
import PageHeader from "@/components/common/PageHeader";
import { useAuthStore } from "@/store/authStore";

export default function ProfilePage() {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const setUser = useAuthStore((state) => state.setUser);
  const query = useQuery({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
  });
  useEffect(() => {
    if (query.data) {
      form.setFieldsValue(query.data);
      setUser(query.data);
    }
  }, [form, query.data, setUser]);
  const save = useMutation({
    mutationFn: updateUser,
    onSuccess: () => message.success("用户资料已更新"),
  });
  return (
    <div className="page">
      <PageHeader title="用户资料" subtitle="第一阶段不维护用户头像。" />
      <Card className="soft-card" loading={query.isLoading}>
        <Form form={form} layout="vertical" onFinish={(values) => save.mutate(values)}>
          <Form.Item name="username" label="用户名">
            <Input />
          </Form.Item>
          <Form.Item name="nickname" label="昵称">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            保存
          </Button>
        </Form>
      </Card>
    </div>
  );
}
