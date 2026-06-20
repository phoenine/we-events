import type { ApiList } from "@/types/api";

type Identified = { id: string };

export function removeIdsFromApiList<T extends Identified>(
  data: ApiList<T> | undefined,
  ids: readonly string[]
): ApiList<T> | undefined {
  if (!data) return data;

  const targets = new Set(ids);
  const list = data.list.filter((item) => !targets.has(item.id));
  const removed = data.list.length - list.length;
  if (!removed) return data;

  return { list, total: Math.max(0, data.total - removed) };
}

export function removeIdsFromList<T extends Identified>(
  data: T[] | undefined,
  ids: readonly string[]
): T[] | undefined {
  if (!data) return data;

  const targets = new Set(ids);
  const list = data.filter((item) => !targets.has(item.id));
  return list.length === data.length ? data : list;
}
