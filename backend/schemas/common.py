from pydantic import BaseModel
from typing import Optional, Any


class BaseResponse(BaseModel):
    # 统一响应结构（便于前后端约定）
    code: int = 0
    message: str = "success"
    data: Optional[Any] = None


def success_response(data=None, message="success") -> dict[str, Any]:
    # 快速构造成功响应
    return {"code": 0, "message": message, "data": data}


def error_response(code: int, message: str, data=None) -> dict[str, Any]:
    # 快速构造错误响应
    return {"code": code, "message": message, "data": data}


def format_search_kw(keyword: str):
    """
    格式化搜索关键词为单词列表
    返回关键词列表, 用于在Supabase查询中进行OR搜索
    """
    # 将常见分隔符统一为空格，便于拆分
    words = keyword.replace("-", " ").replace("|", " ").split(" ")
    # 过滤空字符串
    words = [word.strip() for word in words if word.strip()]
    return words
