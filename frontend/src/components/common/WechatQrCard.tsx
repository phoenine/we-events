import { QrcodeOutlined, QuestionCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Card, Image, Space, Spin, Tag } from "antd";
import { useEffect, useRef, useState } from "react";
import { getQrStatus, getQrUrl, requestQrCode } from "@/api/auth";

type QrState = "idle" | "loading" | "waiting" | "success" | "error";

type WechatQrCardProps = {
  statusColor?: string;
  statusLabel?: string;
  statusMessage?: string;
};

export default function WechatQrCard({ statusColor = "default", statusLabel = "未授权", statusMessage }: WechatQrCardProps) {
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
          setQrUrl("");
          setState("success");
        }
      }, 3000);
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "二维码申请失败");
    }
  };

  const stateTag =
    state === "waiting" ? (
      <Tag color="processing">等待扫码确认</Tag>
    ) : state === "success" ? (
      <Tag color="success">授权成功</Tag>
    ) : state === "error" ? (
      <Tag color="error">{error || "授权异常"}</Tag>
    ) : null;
  const shouldShowQrPanel = statusColor !== "success" || state === "loading" || state === "waiting" || Boolean(qrUrl);

  return (
    <Card className="soft-card qr-card system-qr-card">
      <div className="system-card-title-row">
        <div>
          <h2>公众号扫码授权</h2>
          <p>采集登录态由系统维护，普通用户只读取已采集数据。</p>
        </div>
        <Tag color={statusColor}>{statusLabel}</Tag>
      </div>
      {shouldShowQrPanel && (
        <div className="qr-display-panel">
          {state === "loading" && (
            <Space className="qr-loading-state">
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
          {!qrUrl && state !== "loading" && (
            <div className="qr-placeholder-card">
              <QrcodeOutlined />
            </div>
          )}
          <span>扫码后更新公众号登录态</span>
        </div>
      )}
      <div className="system-qr-actions">
        {stateTag}
        <Button type="primary" icon={<ReloadOutlined />} onClick={start} loading={state === "loading"}>
          {statusColor === "success" && state === "idle" ? "重新申请" : state === "idle" ? "申请二维码" : "重新申请"}
        </Button>
      </div>
      <div className={`system-auth-note ${statusColor === "success" ? "system-auth-note-success" : ""}`}>
        <QuestionCircleOutlined />
        <p>{statusMessage || "微信登录态无法保证永久保活，过期或采集失败时重新扫码。"}</p>
      </div>
    </Card>
  );
}
