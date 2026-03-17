"""
OpenClaw 飞书集成：以用户身份发消息到指定群组、监听机器人回复。
"""
import os
import sys
import time
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Any, Callable, Dict, List, Optional

import requests
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    OPENCLAW_GATEWAY_URL,
    OPENCLAW_GATEWAY_TOKEN,
    FEISHU_APP_ID as _CFG_FEISHU_APP_ID,
    FEISHU_APP_SECRET as _CFG_FEISHU_APP_SECRET,
    FEISHU_BASE_URL as _CFG_FEISHU_BASE_URL,
    FEISHU_TARGET_CHAT_ID,
    FEISHU_VERIFICATION_TOKEN,
    FEISHU_ENCRYPT_KEY,
)

OPENCLAW_URL = OPENCLAW_GATEWAY_URL
OPENCLAW_TOKEN = OPENCLAW_GATEWAY_TOKEN
FEISHU_APP_ID = _CFG_FEISHU_APP_ID
FEISHU_APP_SECRET = _CFG_FEISHU_APP_SECRET
FEISHU_BASE_URL = _CFG_FEISHU_BASE_URL


# ============================================================
# 飞书 API 客户端
# ============================================================

class FeishuClient:
    """飞书应用级 API 客户端（app_access_token）。"""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn",
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._token: Optional[str] = None
        self._NO_PROXY = {"http": None, "https": None}

    def _get_tenant_token(self) -> str:
        if self._token:
            return self._token
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        r = requests.post(
            url,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=15,
            proxies=self._NO_PROXY,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_token 失败：{data}")
        self._token = data["tenant_access_token"]
        return self._token

    def list_chat_members(self, chat_id: str) -> List[Dict[str, Any]]:
        """获取群成员列表（含机器人）。"""
        token = self._get_tenant_token()
        url = f"{self.base_url}/open-apis/im/v1/chats/{chat_id}/members"
        members: List[Dict[str, Any]] = []
        page_token = ""
        while True:
            params = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=15,
                proxies=self._NO_PROXY,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                raise RuntimeError(f"获取群成员失败：{data}")
            items = data.get("data", {}).get("items", [])
            for it in items:
                mid = it.get("member_id", "")
                mtype = it.get("member_id_type", "")
                name = it.get("name", "(未命名)")
                members.append({"member_id": mid, "member_id_type": mtype, "name": name})
            page_token = data.get("data", {}).get("page_token", "")
            if not page_token:
                break
        return members


class FeishuUserAuth:
    """
    飞书用户 OAuth 授权，获取用户 access_token，
    用于以用户身份发送消息（可触发机器人回复）。
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn",
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._NO_PROXY = {"http": None, "https": None}
        self._cache_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".feishu_user_token.json"
        )

    def _run_oauth_server(self, redirect_uri: str, state: str) -> str:
        """启动本地服务器等待 OAuth 回调，返回 code。"""
        code_holder: List[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(s):
                parsed = urlparse(s.path)
                qs = parse_qs(parsed.query)
                if qs.get("state", [""])[0] != state:
                    s.send_response(400)
                    s.end_headers()
                    s.wfile.write(b"state mismatch")
                    return
                code_holder.append(qs.get("code", [""])[0])
                s.send_response(200)
                s.send_header("Content-type", "text/html; charset=utf-8")
                s.end_headers()
                s.wfile.write(
                    "<html><body><h2>授权成功，请关闭此窗口</h2></body></html>".encode("utf-8")
                )

            def log_message(s, fmt, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        url = f"{redirect_uri}?state={state}&port={port}"
        webbrowser.open(url)
        server.handle_request()
        server.server_close()
        return code_holder[0] if code_holder else ""

    def get_user_access_token(self) -> str:
        """获取用户 access_token，优先缓存，否则 OAuth。"""
        cache: Dict[str, Any] = {}
        try:
            if os.path.isfile(self._cache_file):
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                expires_at = cache.get("expires_at", 0)
                if expires_at > time.time() + 60:
                    return cache["access_token"]
                refresh = cache.get("refresh_token")
                if refresh:
                    url = f"{self.base_url}/open-apis/authen/v1/refresh_access_token"
                    r = requests.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={
                            "grant_type": "refresh_token",
                            "refresh_token": refresh,
                            "app_id": self.app_id,
                            "app_secret": self.app_secret,
                        },
                        timeout=15,
                        proxies=self._NO_PROXY,
                    )
                    r.raise_for_status()
                    data = r.json()
                    if data.get("code") == 0:
                        d = data.get("data", {})
                        cache["access_token"] = d["access_token"]
                        cache["refresh_token"] = d.get("refresh_token", refresh)
                        cache["expires_at"] = time.time() + d.get("expire", 7200) - 300
                        with open(self._cache_file, "w", encoding="utf-8") as f:
                            json.dump(cache, f, ensure_ascii=False, indent=2)
                        return cache["access_token"]
        except Exception as e:
            print(f"[auth] 读取/刷新缓存失败: {e}")
        # 需要完整 OAuth
        from secrets import token_urlsafe
        state = token_urlsafe(16)
        redirect_uri = "https://open.feishu.cn/document/ukTMukTMukTM/ukTNzUKL5UzM4UvL2NzN"
        # 简化：用飞书 AppLink 或手动复制 code
        print("[auth] 请完成飞书 OAuth 授权...")
        auth_url = (
            f"{self.base_url}/open-apis/authen/v1/authorize"
            f"?app_id={self.app_id}&redirect_uri={redirect_uri}&state={state}&scope=auth:user.id:read%20im:message%20im:message.send_as_user%20im:message:send_as_bot"
        )
        webbrowser.open(auth_url)
        code = input("请输入授权后重定向 URL 中的 code 参数: ").strip()
        if not code:
            raise RuntimeError("未获取到 code")
        url = f"{self.base_url}/open-apis/authen/v1/oidc/access_token"
        r = requests.post(
            url,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
            timeout=15,
            proxies=self._NO_PROXY,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"换取 token 失败：{data}")
        d = data.get("data", {})
        cache = {
            "access_token": d["access_token"],
            "refresh_token": d.get("refresh_token", ""),
            "expires_at": time.time() + d.get("expire", 7200) - 300,
        }
        with open(self._cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        return cache["access_token"]

    def get_user_info(self) -> Dict[str, Any]:
        """获取当前授权用户的信息（含 open_id）。"""
        user_token = self.get_user_access_token()
        url = f"{self.base_url}/open-apis/authen/v1/user_info"
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
            proxies=self._NO_PROXY,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取用户信息失败：{data}")
        return data.get("data", {})

    def send_text_as_user(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "chat_id",
    ) -> Dict[str, Any]:
        """以用户身份发送文本消息。receive_id_type: chat_id | open_id"""
        user_token = self.get_user_access_token()
        url = f"{self.base_url}/open-apis/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }
        r = requests.post(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {user_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
            proxies=self._NO_PROXY,
        )
        if not r.ok:
            raise RuntimeError(f"以用户身份发送消息失败（{r.status_code}）：{r.text}")
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"以用户身份发送消息失败：{data}")
        return data


# 全局：飞书 Webhook 收到的群消息，供 FeishuReplyWaiter 读取
# key=chat_id, value=[(create_time_ms, text), ...]
_feishu_chat_replies: Dict[str, List[tuple]] = {}
_feishu_replies_lock = threading.Lock()


def _on_feishu_message(data: P2ImMessageReceiveV1) -> None:
    """Webhook 收到群消息时调用，写入全局 store 供 waiter 读取。"""
    try:
        event = data.event
        if not event:
            return
        msg = event.message
        chat_id = getattr(msg, "chat_id", None) or (msg and getattr(msg, "chat_id", ""))
        if not chat_id:
            return
        content = getattr(msg, "content", None) or getattr(msg, "body", None) or ""
        if isinstance(content, str):
            try:
                parsed = json.loads(content) if content else {}
            except Exception:
                parsed = {}
        else:
            parsed = content if isinstance(content, dict) else {}
        text = parsed.get("text", "") if isinstance(parsed, dict) else ""
        if not text:
            return
        create_time = getattr(msg, "create_time", None) or 0
        try:
            ts_val = int(create_time) if create_time else 0
        except (TypeError, ValueError):
            ts_val = 0
        with _feishu_replies_lock:
            if chat_id not in _feishu_chat_replies:
                _feishu_chat_replies[chat_id] = []
            _feishu_chat_replies[chat_id].append((ts_val, text))
    except Exception as e:
        print(f"[openclaw] Webhook 处理消息异常: {e}")


def get_feishu_event_handler():
    """返回用于 webhook 的 EventDispatcherHandler，需在 app 中挂载 POST 路由。"""
    vtoken = FEISHU_VERIFICATION_TOKEN or ""
    ekey = FEISHU_ENCRYPT_KEY or ""
    return lark.EventDispatcherHandler.builder(vtoken, ekey).register_p2_im_message_receive_v1(_on_feishu_message).build()


class FeishuReplyWaiter:
    """监听飞书消息事件，等待指定会话中的新消息（用于收机器人回复）。
    消息来源：飞书 Webhook（/api/feishu/event）需在开发者后台配置。"""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        target_chat_id: str,
        exclude_app_id: Optional[str] = None,
        base_url: str = "https://open.feishu.cn",
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.target_chat_id = target_chat_id
        self.exclude_app_id = exclude_app_id or app_id
        self.base_url = base_url
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def wait(self, sent_at: float, timeout: float) -> Optional[str]:
        """等待 sent_at 之后的新回复，最多 timeout 秒。从全局 _feishu_chat_replies 读取（由 Webhook 写入）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with _feishu_replies_lock:
                replies = _feishu_chat_replies.get(self.target_chat_id, [])
                for i, (ts, txt) in enumerate(replies):
                    if ts / 1000 > sent_at:
                        _feishu_chat_replies[self.target_chat_id].pop(i)
                        return txt
            time.sleep(0.5)
        return None


def send_as_user_and_wait_reply(
    command: str,
    *,
    chat_id: str | None = None,
    timeout: float = 120.0,
    wait: bool = True,
    app_id: str | None = None,
    app_secret: str | None = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    extend_check: Optional[Callable[[], bool]] = None,
) -> Optional[str]:
    """
    以【用户身份】向飞书指定群组发指令。当 wait=True 时等待 OpenClaw 回复；wait=False 则仅发送不等待。
    cancel_check: 返回 True 时停止等待。
    extend_check: 返回 True 时延长 60 秒等待时间。
    """
    _app_id = app_id or FEISHU_APP_ID
    _app_secret = app_secret or FEISHU_APP_SECRET
    user_auth = FeishuUserAuth(app_id=_app_id, app_secret=_app_secret)
    target_chat_id = chat_id or FEISHU_TARGET_CHAT_ID

    waiter = FeishuReplyWaiter(
        app_id=_app_id,
        app_secret=_app_secret,
        target_chat_id=target_chat_id,
        exclude_app_id=_app_id,
    )
    waiter.start()
    try:
        sent_at = time.time()
        user_auth.send_text_as_user(receive_id=target_chat_id, text=command, receive_id_type="chat_id")
        print(f"[openclaw] 已以用户身份发送指令到群聊：{command!r}")
        if not wait:
            print("[openclaw] 不等待回复，已返回。")
            return None
        print(f"[openclaw] 等待 OpenClaw 回复（最多 {timeout} 秒）...")
        if cancel_check or extend_check:
            chunk = 10.0
            elapsed = 0.0
            while elapsed < timeout:
                wait_sec = min(chunk, timeout - elapsed)
                reply = waiter.wait(sent_at=sent_at, timeout=wait_sec)
                if reply is not None:
                    print(f"[openclaw] 收到回复（{len(reply)} 字）。")
                    return reply
                elapsed += wait_sec
                if cancel_check and cancel_check():
                    print(f"[openclaw] 用户选择跳过等待。")
                    return None
                if extend_check and extend_check():
                    elapsed = max(0, elapsed - 60)
                    print(f"[openclaw] 用户选择再等待 60 秒，剩余时间延长。")
        else:
            reply = waiter.wait(sent_at=sent_at, timeout=timeout)
            if reply is None:
                print(f"[openclaw] 超时（{timeout}s），未收到回复。")
            else:
                print(f"[openclaw] 收到回复（{len(reply)} 字）。")
            return reply
    finally:
        waiter.stop()


if __name__ == "__main__":
    from config import TEST_TASK_TEXT
    print("[openclaw] 测试发送...")
    reply = send_as_user_and_wait_reply(TEST_TASK_TEXT, timeout=60)
    print(f"[openclaw] 回复: {reply}")
