from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from schemas import success_response, error_response
from core.common.log import logger
from core.integrations.supabase.auth import (
    get_current_user,
    authenticate_user_credentials,
    UserCredentials,
)
from core.integrations.supabase.storage import SupabaseStorage
from core.integrations.supabase.auth_session_store import auth_session_store
from driver.wx.service import (
    get_qr_code as wx_get_qr_code,
    get_state as wx_get_state,
    logout as wx_logout,
    set_current_session_id as wx_set_current_session_id,
)


router = APIRouter(prefix=f"/auth", tags=["认证"])

# 兼容：原先把 session_id 写到 WX_API.current_session_id 上。
# 现在改为按用户保存，避免并发请求串号。
_WX_SESSION_BY_USER_ID: dict[str, str] = {}


def ApiSuccess(session=None, ext_data=None):
    if session is not None:
        logger.info("登录成功")
    else:
        logger.info("登录失败, 请检查上述错误信息")


async def _issue_token(form_data: OAuth2PasswordRequestForm):
    # 使用 Supabase 账号密码认证
    credentials = UserCredentials(
        username=form_data.username, password=form_data.password
    )
    auth_result = await authenticate_user_credentials(credentials)
    return auth_result.model_dump()


@router.get("/qr/code", summary="获取登录二维码")
async def get_qrcode(_current_user=Depends(get_current_user)):
    session_id = None
    if auth_session_store.valid_session_db():
        user_id = _current_user.get("id") or None
        session_id = await auth_session_store.create_session(
            user_id=user_id, expires_minutes=2
        )
        logger.info(f"[wx-auth] create_session user_id={user_id} session_id={session_id}")
        if session_id:
            wx_set_current_session_id(session_id)
            logger.info(f"[wx-auth] set current_session_id={session_id}")
        if user_id and session_id:
            _WX_SESSION_BY_USER_ID[user_id] = session_id
    code_url = wx_get_qr_code(callback=ApiSuccess)
    if session_id:
        code_url = {**code_url, "session_id": session_id}
    return success_response(code_url)


@router.get("/qr/image", summary="获取登录二维码图片")
async def qr_image(_current_user=Depends(get_current_user)):
    state_env = wx_get_state()
    state = state_env.get("data") or {}
    return success_response(state.get("has_code"))


@router.get("/qr/url", summary="获取二维码完整访问地址")
async def qr_url(_current_user=Depends(get_current_user)):
    sb = SupabaseStorage()
    state_env = wx_get_state()
    state = state_env.get("data") or {}
    if not state.get("has_code"):
        return success_response(
            {"image_url": None, "mode": "supabase" if sb.valid() else "local"}
        )
    url = state.get("wx_login_url")
    user_id = _current_user.get("id")
    session_id = _WX_SESSION_BY_USER_ID.get(user_id) if user_id else None
    if url and session_id and auth_session_store.valid_session_db():
        try:
            await auth_session_store.update_session(
                session_id,
                status="waiting",
                qr_signed_url=url,
                expires_minutes=2,
            )
        except Exception:
            pass
    return success_response(
        {"image_url": url, "mode": "supabase" if sb.valid() else "local"}
    )


@router.get("/qr/status", summary="获取扫描状态")
async def qr_status(_current_user=Depends(get_current_user)):
    state_env = wx_get_state()
    state = state_env.get("data") or {}
    return success_response(
        {
            "login_status": state.get("state") == "success",
        }
    )


@router.get("/qr/over", summary="扫码完成")
async def qr_success(_current_user=Depends(get_current_user)):
    return success_response(wx_logout(clear_persisted=False))


@router.post("/token", summary="获取Token")
async def getToken(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        return await _issue_token(form_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=error_response(code=40101, message=f"认证失败: {str(e)}"),
        )


@router.post("/logout", summary="用户注销")
async def logout(current_user: dict = Depends(get_current_user)):
    return {"code": 0, "message": "注销成功"}


@router.post("/refresh", summary="刷新Token")
async def refresh_token(_current_user: dict = Depends(get_current_user)):
    """
    当前基于 Supabase Access Token 的无状态认证模式下，
    如需刷新，请在客户端通过 Supabase Auth 流程重新获取 Token。
    """
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_response(
            code=40001,
            message="当前认证模式下不支持在服务端刷新 Token, 请通过重新登录获取新令牌",
        ),
    )


@router.get("/verify", summary="验证Token有效性")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """验证当前token是否有效"""
    return success_response(
        {
            "is_valid": True,
            "username": current_user["username"],
            "email": current_user.get("email"),
            "user_id": current_user.get("id"),
        }
    )
