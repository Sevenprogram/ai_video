"""
OpenClaw 飞书集成：以用户身份发消息、创建 P2P 会话、监听机器人回复。
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
    OPENCLAW_BOT_OPEN_ID,
    OPENCLAW_BOT_APP_ID,
    OPENCLAW_P2P_CHAT_ID,
    OPENCLAW_USE_P2P,
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

    def create_p2p_chat(
        self,
        user_open_id: str,
        bot_app_id: str,
    ) -> str:
        """
        创建与指定机器人的 P2P 会话，返回 chat_id。
        用于绕过 open_id cross app 限制。
        """
        token = self._get_tenant_token()
        url = f"{self.base_url}/open-apis/im/v1/chats"
        payload = {
            "name": "P2P",
            "chat_mode": "p2p",
            "chat_type": "p2p",
            "user_id_list": [user_open_id],
            "bot_id_list": [bot_app_id],
        }
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=15,
            proxies=self._NO_PROXY,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"创建 P2P 会话失败：{data}")
        chat_id = data.get("data", {}).get("chat_id", "")
        if not chat_id:
            raise RuntimeError("创建 P2P 会话返回的 chat_id 为空")
        return chat_id


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


class FeishuReplyWaiter:
    """监听飞书消息事件，等待指定会话中的新消息（用于收机器人回复）。"""

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
        self._replies: List[tuple] = []
        self._lock = threading.Lock()
        self._running = False
        self._client: Optional[lark.Client] = None
        self._dispatcher: Optional[lark.event.Dispatcher] = None

    def _handler(self, data: P2ImMessageReceiveV1) -> None:
        try:
            event = data.event
            if not event:
                return
            msg = event.message
            chat_id = getattr(msg, "chat_id", None) or (msg and getattr(msg, "chat_id", ""))
            if chat_id != self.target_chat_id:
                return
            sender = event.sender
            sender_app_id = getattr(sender, "sender_type", None)
            if str(getattr(sender, "sender_id", {}).get("open_id", "")) == self.exclude_app_id:
                return
            if hasattr(sender, "sender_id") and isinstance(sender.sender_id, dict):
                if sender.sender_id.get("app_id") == self.exclude_app_id:
                    return
            body = getattr(msg, "body", {}) or {}
            if isinstance(body, str):
                import json
                try:
                    body = json.loads(body) if body else {}
                except Exception:
                    body = {}
            text = body.get("text", "") if isinstance(body, dict) else ""
            if not text:
                return
            create_time = getattr(msg, "create_time", None) or 0
            with self._lock:
                self._replies.append((create_time, text))
        except Exception as e:
            print(f"[waiter] 处理事件异常: {e}")

    def start(self) -> None:
        self._running = True
        self._client = lark.Client.builder().app_id(self.app_id).app_secret(self.app_secret).build()
        self._dispatcher = lark.event.Dispatcher.builder("", "").register_p2_im_message_receive_v1(self._handler).build()
        # 使用轮询模拟：实际项目中可用 WebSocket 订阅
        # 此处简化，不启动独立线程，由 wait() 轮询

    def stop(self) -> None:
        self._running = False

    def wait(self, sent_at: float, timeout: float) -> Optional[str]:
        """等待 sent_at 之后的新回复，最多 timeout 秒。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, (ts, txt) in enumerate(self._replies):
                    if ts / 1000 > sent_at:
                        self._replies.pop(i)
                        return txt
            time.sleep(0.5)
        return None


_P2P_CHAT_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".feishu_p2p_chat_id")


def _get_openclaw_p2p_chat_id(user_auth: "FeishuUserAuth") -> Optional[str]:
    """获取与 OpenClaw 的 P2P chat_id。优先 config，否则创建并缓存。"""
    if OPENCLAW_P2P_CHAT_ID and OPENCLAW_P2P_CHAT_ID.strip():
        return OPENCLAW_P2P_CHAT_ID.strip()
    if not OPENCLAW_BOT_APP_ID or not OPENCLAW_BOT_APP_ID.startswith("cli_"):
        return None
    try:
        if os.path.isfile(_P2P_CHAT_CACHE_FILE):
            with open(_P2P_CHAT_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = f.read().strip()
                if cached and cached.startswith("oc_"):
                    return cached
    except Exception:
        pass
    try:
        user_info = user_auth.get_user_info()
        user_open_id = user_info.get("open_id") or user_info.get("user_id")
        if not user_open_id:
            return None
        client = FeishuClient(app_id=FEISHU_APP_ID, app_secret=FEISHU_APP_SECRET)
        chat_id = client.create_p2p_chat(user_open_id=user_open_id, bot_app_id=OPENCLAW_BOT_APP_ID)
        try:
            with open(_P2P_CHAT_CACHE_FILE, "w", encoding="utf-8") as f:
                f.write(chat_id)
        except Exception:
            pass
        return chat_id
    except Exception as e:
        print(f"[openclaw] 创建 P2P 会话失败: {e}")
        return None


def send_as_user_and_wait_reply(
    command: str,
    *,
    chat_id: str | None = None,
    timeout: float = 120.0,
    app_id: str | None = None,
    app_secret: str | None = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Optional[str]:
    """
    以【用户身份】向飞书发指令，然后等待 OpenClaw 的回复。
    当 OPENCLAW_USE_P2P=True 时，发到机器人私聊；否则发到群聊。
    """
    _app_id = app_id or FEISHU_APP_ID
    _app_secret = app_secret or FEISHU_APP_SECRET
    user_auth = FeishuUserAuth(app_id=_app_id, app_secret=_app_secret)
    target_chat_id: Optional[str] = None
    if OPENCLAW_USE_P2P:
        target_chat_id = _get_openclaw_p2p_chat_id(user_auth)
        if not target_chat_id:
            raise RuntimeError(
                "OPENCLAW_USE_P2P=True 但无法获取 P2P chat_id。"
                "请运行 python3 get_p2p_chat_id.py 获取 chat_id，并填入 config.py 的 OPENCLAW_P2P_CHAT_ID。"
            )
    else:
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
        mode = "P2P 私聊" if OPENCLAW_USE_P2P else "群聊"
        print(f"[openclaw] 已以用户身份发送指令到 {mode}：{command!r}")
        print(f"[openclaw] 等待 OpenClaw 回复（最多 {timeout} 秒）...")
        if cancel_check:
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
        else:
            reply = waiter.wait(sent_at=sent_at, timeout=timeout)
            if reply is None:
                print(f"[openclaw] 超时（{timeout}s），未收到回复。")
            else:
                print(f"[openclaw] 收到回复（{len(reply)} 字）。")
            return reply
    finally:
        waiter.stop()


def send_as_user_p2p_and_wait_reply(
    command: str,
    *,
    bot_open_id: str | None = None,
    timeout: float = 120.0,
    app_id: str | None = None,
    app_secret: str | None = None,
) -> Optional[str]:
    """
    以【用户身份】向指定机器人发起私聊，并等待其回复。
    使用 open_id 时可能遇到 cross app 错误，建议使用 send_as_user_and_wait_reply + OPENCLAW_USE_P2P。
    """
    return send_as_user_and_wait_reply(command, timeout=timeout, app_id=app_id, app_secret=app_secret)


if __name__ == "__main__":
    from config import TEST_TASK_TEXT
    print("[openclaw] 测试发送...")
    reply = send_as_user_and_wait_reply(TEST_TASK_TEXT, timeout=60)
    print(f"[openclaw] 回复: {reply}")
