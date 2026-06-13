from typing import TypedDict, Any, Optional, List, Literal


class WxMpSession(TypedDict, total=False):
    """公众号后台会话结构"""

    cookies: list[dict]
    cookies_str: str
    token: str
    wx_login_url: str
    user_agent: str
    expiry: Optional[dict]
    ext_data: Any
    updated_at: int


class WxMpInfo(TypedDict, total=False):
    """文章页中提取到的公众号信息结构"""

    mp_name: str
    logo: str
    biz: str       # 公众号 biz 标识（用于拼接文章、接口请求等）


class WxArticleInfo(TypedDict, total=False):
    """文章抓取返回结构"""

    id: str
    title: str
    publish_time: Any
    content: str
    images: List[str]
    mp_info: WxMpInfo
    wechat_account_id: str
    pic_url: str
    description: str
    topic_image: str        # 话题 / 专题头图（如有）


# 对外错误码（稳定契约）：wx_service 会将底层异常/哨兵值统一映射到这些 code。
WxErrorCode = Literal[
    "WX_NOT_LOGGED_IN",
    "WX_SESSION_EXPIRED",
    "WX_QR_NOT_READY",
    "WX_CAPTCHA_REQUIRED",
    "WX_ENV_BLOCKED",
    "WX_ARTICLE_DELETED",
    "WX_ARTICLE_RESTRICTED",
    "WX_ARTICLE_PARSE_FAILED",
    "WX_NETWORK_TIMEOUT",
    "WX_INTERNAL_ERROR",
]


class WxError(TypedDict, total=False):
    """统一错误对象（对外稳定字段）。

    字段约定：
    - code: 稳定错误码
    - message: 面向用户/调用方的简要错误信息
    - reason: 更细粒度原因
    - retryable: 是否建议重试
    - stage: 发生阶段
    - raw: 原始信息
    """

    code: WxErrorCode
    message: str
    reason: Optional[str]
    retryable: bool
    stage: str
    raw: Optional[str]


class WxEnvelope(TypedDict, total=False):
    """统一的Envelope

    说明：
    - wx_service 作为 Facade 的唯一出口，应尽量让所有对外能力都返回该结构。
    - ok 为唯一判定成功/失败的字段：
      - ok=True  => data 应包含成功结果
      - ok=False => error 应包含错误对象

    字段说明：
    - ok: 是否成功
    - data: 成功结果（结构由具体接口决定，如 WxArticleInfo / session info 等）
    - error: 失败时的 WxError
    - state: 可选, 登录流程相关的状态
    """

    ok: bool
    data: Any
    error: WxError
    state: Optional[str]


class WxDriverError(Exception):
    def __init__(
        self,
        *,
        code: WxErrorCode,
        message: str,
        reason: Optional[str] = None,
        retryable: bool = False,
        stage: str = "driver",
        raw: Optional[str] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.reason = reason
        self.retryable = retryable
        self.stage = stage
        self.raw = raw


class WxArticleError(WxDriverError):
    def __init__(
        self,
        *,
        code: WxErrorCode,
        message: str,
        reason: Optional[str] = None,
        retryable: bool = False,
        stage: str = "article",
        raw: Optional[str] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            reason=reason,
            retryable=retryable,
            stage=stage,
            raw=raw,
        )
