import { useMutation } from "@tanstack/react-query";
import { App, Button, Card, Form, Input } from "antd";
import { changePassword } from "@/api/user";
import PageHeader from "@/components/common/PageHeader";

export default function ChangePasswordPage() {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const mutation = useMutation({
    mutationFn: changePassword,
    onSuccess: () => {
      message.success("密码已修改");
      form.resetFields();
    },
  });
  return (
    <div className="page">
      <PageHeader title="修改密码" subtitle="使用当前密码验证后更新登录密码。" />
      <Card className="soft-card">
        <Form form={form} layout="vertical" onFinish={(values) => mutation.mutate(values)} style={{ maxWidth: 460 }}>
          <Form.Item name="old_password" label="当前密码" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 8 }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={mutation.isPending}>
            修改密码
          </Button>
        </Form>
      </Card>
    </div>
  );
}
