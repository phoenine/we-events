import os
from typing import Optional, Dict, List, Union, Any, cast
from supabase import create_client, Client, ClientOptions

from core.integrations.supabase.settings import settings
from core.common.log import logger



class SupabaseClient:
    """Supabase数据库客户端"""

    def __init__(self):
        self.url = settings.url
        self.key = settings.service_key
        self.client: Optional[Client] = None
        self._initialized = False

    def init(self):
        """初始化Supabase客户端"""
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL和SUPABASE_SERVICE_KEY环境变量必须设置")

        if self._initialized:
            return

        try:
            # 使用服务角色密钥以绕过RLS限制
            # 自定义 httpx client，禁用 SSL 验证以避免一些 TLS 兼容性问题
            import httpx
            transport = httpx.HTTPTransport(retries=2)
            custom_client = httpx.Client(transport=transport, verify=False)
            options = ClientOptions(httpx_client=custom_client)
            self.client = create_client(self.url, self.key, options=options)
            self._initialized = True
            logger.info("Supabase客户端初始化成功")
        except Exception as e:
            logger.error(f"Supabase客户端初始化失败: {e}")
            raise

    def get_client(self) -> Client:
        """获取Supabase客户端实例"""
        if not self._initialized or not self.client:
            self.init()

        if not self.client:
            raise RuntimeError("Supabase客户端尚未成功初始化")

        return self.client

    def from_table(self, table_name: str):
        """获取表操作对象"""
        return self.get_client().table(table_name)

    def _apply_order(self, query: Any, order: str):
        """
        兼容项目内常用排序写法：
        - "created_at"
        - "created_at.asc"
        - "created_at.desc"
        - "created_at.desc,publish_at.asc"
        """
        tokens = [seg.strip() for seg in str(order).split(",") if seg.strip()]
        for token in tokens:
            parts = token.split(".")
            column = parts[0].strip()
            if not column:
                continue

            direction = parts[1].lower() if len(parts) > 1 else "asc"
            desc = direction == "desc"
            query = query.order(column, desc=desc)
        return query

    #! 以下为基础CRUD操作
    async def select(
        self,
        table: str,
        filters: Optional[Dict] = None,
        columns: str = "*",
        order: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ):
        """查询数据"""
        try:
            query = self.from_table(table).select(columns)

            # 添加过滤条件
            if filters:
                for key, value in filters.items():
                    if isinstance(value, dict):
                        for op, val in value.items():
                            if op == "gt":
                                query = query.gt(key, val)
                            elif op == "gte":
                                query = query.gte(key, val)
                            elif op == "lt":
                                query = query.lt(key, val)
                            elif op == "lte":
                                query = query.lte(key, val)
                            elif op == "neq":
                                query = query.neq(key, val)
                            elif op == "like":
                                query = query.like(key, val)
                            elif op == "ilike":
                                query = query.ilike(key, val)
                            elif op == "in":
                                query = query.in_(key, val)
                    else:
                        query = query.eq(key, value)

            # 添加排序
            if order:
                query = self._apply_order(query, order)

            # 添加分页
            if limit:
                query = query.limit(limit)
            if offset:
                query = query.offset(offset)

            response = query.execute()
            return response.data if response.data else []

        except Exception as e:
            logger.error(f"查询表 {table} 失败: {e}")
            raise

    async def count(self, table: str, filters: Optional[Dict] = None):
        """统计记录数量"""
        try:
            query = self.from_table(table).select("*", count=cast(Any, "exact"))
            if filters:
                for key, value in filters.items():
                    if isinstance(value, dict):
                        # 支持复杂查询条件，如{"gt": 10}
                        for op, val in value.items():
                            if op == "gt":
                                query = query.gt(key, val)
                            elif op == "gte":
                                query = query.gte(key, val)
                            elif op == "lt":
                                query = query.lt(key, val)
                            elif op == "lte":
                                query = query.lte(key, val)
                            elif op == "neq":
                                query = query.neq(key, val)
                            elif op == "like":
                                query = query.like(key, val)
                            elif op == "ilike":
                                query = query.ilike(key, val)
                            elif op == "in":
                                query = query.in_(key, val)
                    else:
                        query = query.eq(key, value)

            response = query.execute()
            data = response.data or []
            return response.count if hasattr(response, "count") else len(data)

        except Exception as e:
            logger.error(f"统计表 {table} 记录数量失败: {e}")
            return 0

    async def insert(self, table: str, data: Dict):
        """插入数据"""
        try:
            response = self.from_table(table).insert(data).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            logger.error(f"插入数据到表 {table} 失败: {e}")
            raise

    async def update(self, table: str, data: Dict, filters: Dict):
        """更新数据"""
        try:
            query = self.from_table(table).update(data)

            # 添加过滤条件
            for key, value in filters.items():
                query = query.eq(key, value)

            response = query.execute()
            return response.data if response.data else []

        except Exception as e:
            logger.error(f"更新表 {table} 失败: {e}")
            raise

    async def delete(self, table: str, filters: Dict):
        """删除数据"""
        try:
            query = self.from_table(table).delete()

            # 添加过滤条件
            for key, value in filters.items():
                if isinstance(value, dict):
                    # 支持复杂查询条件，如 {"in": [...]} 等
                    for op, val in value.items():
                        if op == "gt":
                            query = query.gt(key, val)
                        elif op == "gte":
                            query = query.gte(key, val)
                        elif op == "lt":
                            query = query.lt(key, val)
                        elif op == "lte":
                            query = query.lte(key, val)
                        elif op == "neq":
                            query = query.neq(key, val)
                        elif op == "like":
                            query = query.like(key, val)
                        elif op == "ilike":
                            query = query.ilike(key, val)
                        elif op == "in":
                            query = query.in_(key, val)
                else:
                    query = query.eq(key, value)

            response = query.execute()
            return response.data if response.data else []

        except Exception as e:
            logger.error(f"删除表 {table} 数据失败: {e}")
            raise

    async def upsert(
        self,
        table: str,
        data: Union[Dict, List[Dict]],
        on_conflict: Optional[str] = None,
    ):
        """插入或更新数据"""
        try:
            if on_conflict:
                query = self.from_table(table).upsert(
                    data,
                    on_conflict=on_conflict,
                )
            else:
                query = self.from_table(table).upsert(data)

            response = query.execute()
            rows = response.data or []
            return rows

        except Exception as e:
            logger.error(f"Upsert数据到表 {table} 失败: {e}")
            raise


supabase_client = SupabaseClient()
