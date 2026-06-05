import { Button, Card, Image, Space, Spin, Tag, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { getQrStatus, getQrUrl, requestQrCode } from "@/api/auth";

type QrState = "idle" | "loading" | "waiting" | "success" | "error";

export default function WechatQrCard() {
  const [state, setState] = useState<QrState>("idle");
  const [qrUrl, setQrUrl] = useState("");
  const [error, setError] = useState("");
  const pollRef = useRef<number | null>(null);
  const statusRef = useRef<number | null>(null);

  const clearTimers = () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    if (statusRef.current) window.clearInterval(statusRef.current);
    pollRef.current = null;
    statusRef.current = null;
  };

  useEffect(() => clearTimers, []);

  const start = async () => {
    clearTimers();
    setError("");
    setQrUrl("");
    setState("loading");
    try {
      const first = await requestQrCode();
      if (first.code) {
        setQrUrl(first.code);
        setState("waiting");
      } else {
        let attempts = 0;
        pollRef.current = window.setInterval(async () => {
          attempts += 1;
          if (attempts > 120) {
            clearTimers();
            setState("error");
            setError("二维码生成超时，请重新申请");
            return;
          }
          const url = await getQrUrl();
          if (url) {
            setQrUrl(url);
            setState("waiting");
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }, 1000);
      }
      statusRef.current = window.setInterval(async () => {
        const status = await getQrStatus();
        if (status?.login_status) {
          clearTimers();
          setState("success");
        }
      }, 3000);
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "二维码申请失败");
    }
  };

  return (
    <Card className="soft-card qr-card" title="公众号扫码授权">
      <Space direction="vertical" size={14} style={{ width: "100%" }}>
        <Typography.Text type="secondary">
          公众号登录态由系统维护，普通用户只读取已采集的数据。
        </Typography.Text>
        {state === "loading" && (
          <Space>
            <Spin /> <span>正在生成二维码...</span>
          </Space>
        )}
        {qrUrl && (
          <Image
            src={qrUrl}
            width={220}
            height={220}
            style={{ objectFit: "contain", background: "#fff", borderRadius: 8 }}
          />
        )}
        {state === "waiting" && <Tag color="processing">等待扫码确认</Tag>}
        {state === "success" && <Tag color="success">授权成功</Tag>}
        {state === "error" && <Tag color="error">{error || "授权异常"}</Tag>}
        <Button type="primary" onClick={start} loading={state === "loading"}>
          {state === "idle" ? "申请二维码" : "重新申请二维码"}
        </Button>
      </Space>
    </Card>
  );
}
