import { Empty } from "antd";
import { Sprout } from "lucide-react";

export default function EmptyState({ description = "暂无数据" }: { description?: string }) {
  return (
    <Empty
      image={
        <div className="empty-illustration">
          <Sprout size={30} />
        </div>
      }
      description={description}
    />
  );
}
