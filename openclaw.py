import os
import sys
import time
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Any, Dict, List, Optional

import requests
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

# 优先从 config.py 读取配置
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    OPENCLAW_GATEWAY_URL,
    OPENCLAW_GATEWAY_TOKEN,
    FEISHU_APP_ID as _CFG_FEISHU_APP_ID,
    FEISHU_APP_SECRET as _CFG_FEISHU_APP_SECRET,
    FEISHU_BASE_URL as _CFG_FEISHU_BASE_URL,
    FEISHU_TARGET_CHAT_ID,
    OPENCLAW_BOT_OPEN_ID,
)

# ──────────────────────────────────────────
# 模块级默认配置（统一来自 config.py）
# ──────────────────────────────────────────
OPENCLAW_URL   = OPENCLAW_GATEWAY_URL
OPENCLAW_TOKEN = OPENCLAW_GATEWAY_TOKEN
FEISHU_APP_ID     = _CFG_FEISHU_APP_ID
FEISHU_APP_SECRET = _CFG_FEISHU_APP_SECRET
FEISHU_BASE_URL   = _CFG_FEISHU_BASE_URL


# ──────────────────────────────────────────
# OpenClaw HTTP 客户端（健康检查）
# ──────────────────────────────────────────
class OpenClawClient:
    """极简 OpenClaw HTTP 客户端。"""

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or OPENCLAW_URL).rstrip("/")
        self.token = token or OPENCLAW_TOKEN

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def health_check(self) -> Dict[str, Any]:
        """尝试多个常见 health 路径，返回第一个成功的结果。"""
        candidates = ["/health", "/v1/health", "/api/health", "/status", "/"]
        last: Dict[str, Any] = {"ok": False, "url": None, "status_code": None, "body_preview": None}
        for path in candidates:
            url = f"{self.base_url}{path}"
            try:
                r = requests.get(url, headers=self._headers(), timeout=10)
                last = {"ok": r.ok, "url": url, "status_code": r.status_code, "body_preview": r.text[:500]}
                if r.ok:
                    return last
            except requests.RequestException as e:
                last = {"ok": False, "url": url, "status_code": None, "body_preview": f"{type(e).__name__}: {e}"}
        return last


# ──────────────────────────────────────────
# 飞书客户端：发消息（同步）
# ──────────────────────────────────────────
class FeishuClient:
    """用 App ID / Secret 获取 tenant token，然后发送消息。"""

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.app_id = app_id or FEISHU_APP_ID
        self.app_secret = app_secret or FEISHU_APP_SECRET
        self.base_url = (base_url or FEISHU_BASE_URL).rstrip("/")
        self._tenant_token: Optional[str] = None
        self._tenant_token_expire_at: float = 0.0

    def _get_tenant_access_token(self) -> str:
        if not self.app_id or not self.app_secret:
            raise ValueError("请先设置 FEISHU_APP_ID 与 FEISHU_APP_SECRET。")
        now = time.time()
        if self._tenant_token and now < self._tenant_token_expire_at - 60:
            return self._tenant_token
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal/"
        r = requests.post(
            url,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取飞书 tenant_access_token 失败：{data}")
        token = data["tenant_access_token"]
        expire = float(data.get("expire", 3600) or 3600)
        self._tenant_token = token
        self._tenant_token_expire_at = now + expire
        return token

    def send_text_to_chat(
        self,
        chat_id: str,
        text: str,
        mention_user_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        发送文本消息到群聊。

        参数：
        - mention_user_id: 若需要 @ 某个机器人/用户，传入其 open_id（如 ou_xxx）。
          飞书的 @ 不是文本，必须用专用格式，纯文字 "@名字" 无效。
        """
        token = self._get_tenant_access_token()
        url = f"{self.base_url}/open-apis/im/v1/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        if mention_user_id:
            # 使用富文本格式实现真正的 @mention
            content = {
                "zh_cn": {
                    "content": [[
                        {"tag": "at", "user_id": mention_user_id},
                        {"tag": "text", "text": f" {text}"},
                    ]]
                }
            }
            msg_type = "post"
        else:
            content = {"text": text}
            msg_type = "text"

        payload = {
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False),
        }
        r = requests.post(
            url,
            params={"receive_id_type": "chat_id"},
            headers=headers,
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书发送消息失败：{data}")
        return data

    def list_chat_members(self, chat_id: str) -> List[Dict[str, Any]]:
        """
        获取群成员列表（含机器人），用于查找 OpenClaw 的 open_id。

        返回：成员列表，每项包含 open_id、name、member_id_type 等字段。
        """
        token = self._get_tenant_access_token()
        url = f"{self.base_url}/open-apis/im/v1/chats/{chat_id}/members"
        headers = {"Authorization": f"Bearer {token}"}
        members: List[Dict[str, Any]] = []
        page_token = ""

        while True:
            params: Dict[str, Any] = {"member_id_type": "open_id", "page_size": 100}
            if page_token:
                params["page_token"] = page_token
            r = requests.get(url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                raise RuntimeError(f"获取群成员失败：{data}")
            items = data.get("data", {}).get("items", [])
            members.extend(items)
            page_token = data.get("data", {}).get("page_token", "")
            if not data.get("data", {}).get("has_more"):
                break

        return members


# ──────────────────────────────────────────
# 飞书 WebSocket 监听器：等待机器人回复
# ──────────────────────────────────────────
# 飞书用户身份授权（OAuth 2.0）
# ──────────────────────────────────────────
class FeishuUserAuth:
    """
    通过浏览器 OAuth 获取用户 access_token，以用户身份发消息。

    用户消息可以触发 OpenClaw 等机器人响应（机器人消息无法触发其他机器人）。

    token 会缓存到本地文件，2 小时内无需重复授权。
    """

    REDIRECT_URI = "http://localhost:9999/callback"
    TOKEN_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".feishu_user_token.json")

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.app_id = app_id or FEISHU_APP_ID
        self.app_secret = app_secret or FEISHU_APP_SECRET
        self.base_url = (base_url or FEISHU_BASE_URL).rstrip("/")

    # 所有 HTTP 请求都绕过系统代理，避免 VPN/代理软件干扰
    _NO_PROXY = {"http": "", "https": ""}

    def _post(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", 15)
        kwargs.setdefault("proxies", self._NO_PROXY)
        r = requests.post(url, **kwargs)
        r.raise_for_status()
        return r

    def _get_app_access_token(self) -> str:
        url = f"{self.base_url}/open-apis/auth/v3/app_access_token/internal/"
        r = self._post(url, json={"app_id": self.app_id, "app_secret": self.app_secret})
        return r.json()["app_access_token"]

    def _exchange_code(self, code: str) -> Dict[str, Any]:
        """用授权码换取 user_access_token 和 refresh_token（新版 OIDC 接口）。"""
        app_token = self._get_app_access_token()
        url = f"{self.base_url}/open-apis/authen/v1/oidc/access_token"
        r = self._post(
            url,
            headers={"Authorization": f"Bearer {app_token}", "Content-Type": "application/json"},
            json={"grant_type": "authorization_code", "code": code},
        )
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"换取用户 token 失败：{data}")
        return data["data"]

    def _refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """用 refresh_token 刷新 user_access_token（新版 OIDC 接口）。"""
        app_token = self._get_app_access_token()
        url = f"{self.base_url}/open-apis/authen/v1/oidc/refresh_access_token"
        r = self._post(
            url,
            headers={"Authorization": f"Bearer {app_token}", "Content-Type": "application/json"},
            json={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"刷新用户 token 失败：{data}")
        return data["data"]

    def _load_cache(self) -> Optional[Dict[str, Any]]:
        try:
            with open(self.TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_cache(self, token_data: Dict[str, Any]) -> None:
        token_data["cached_at"] = time.time()
        with open(self.TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)

    def get_user_access_token(self) -> str:
        """
        获取用户 access_token。

        优先使用本地缓存；token 快过期时自动用 refresh_token 刷新；
        完全失效时打开浏览器重新授权。
        """
        cache = self._load_cache()
        now = time.time()

        if cache:
            cached_at = cache.get("cached_at", 0)
            expires_in = cache.get("expires_in", 7200)
            # token 还有 5 分钟以上有效期，直接用
            if now < cached_at + expires_in - 300:
                print("[auth] 使用缓存的用户 token。")
                return cache["access_token"]
            # token 快过期，尝试用 refresh_token 刷新
            refresh_token = cache.get("refresh_token", "")
            if refresh_token:
                try:
                    print("[auth] 用 refresh_token 刷新用户 token...")
                    new_data = self._refresh_token(refresh_token)
                    self._save_cache(new_data)
                    return new_data["access_token"]
                except Exception as e:
                    print(f"[auth] 刷新失败（{e}），需要重新授权。")

        # 打开浏览器授权
        return self._authorize_with_browser()

    def _authorize_with_browser(self) -> str:
        """打开浏览器，用户登录飞书授权，本地 9999 端口接收回调，返回 user_access_token。"""
        code_holder: Dict[str, str] = {}
        done = threading.Event()

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                qs = parse_qs(urlparse(self.path).query)
                code_holder["code"] = qs.get("code", [""])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<html><body><h2>授权成功，可以关闭此页面。</h2></body></html>".encode())
                done.set()

            def log_message(self, *args):
                pass

        server = HTTPServer(("localhost", 9999), _Handler)
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        # scope 使用飞书新版 OIDC 格式（空格分隔多个）
        scopes = " ".join([
            "im:message",
            "im:message:send_as_bot",
        ])
        auth_url = (
            f"{self.base_url}/open-apis/authen/v1/authorize"
            f"?app_id={self.app_id}"
            f"&redirect_uri={self.REDIRECT_URI}"
            f"&scope={requests.utils.quote(scopes)}"
            f"&state=feishu_auth"
        )
        print(f"[auth] 正在打开浏览器进行飞书授权...")
        print(f"[auth] 如果浏览器未自动打开，请手动访问：{auth_url}")
        webbrowser.open(auth_url)

        done.wait(timeout=120)
        server.server_close()

        code = code_holder.get("code", "")
        if not code:
            raise RuntimeError("授权超时或被取消，未收到授权码。")

        print("[auth] 收到授权码，正在换取 token...")
        token_data = self._exchange_code(code)
        self._save_cache(token_data)
        print("[auth] 用户 token 获取成功，已缓存到本地。")
        return token_data["access_token"]

    def send_text_as_user(self, chat_id: str, text: str) -> Dict[str, Any]:
        """以用户身份向群聊发送文本消息（可触发 OpenClaw 等机器人响应）。"""
        user_token = self.get_user_access_token()
        url = f"{self.base_url}/open-apis/im/v1/messages"
        headers = {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        r = requests.post(
            url,
            params={"receive_id_type": "chat_id"},
            headers=headers,
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


# ──────────────────────────────────────────
# 以用户身份发指令 + 监听机器人回复
# ──────────────────────────────────────────
def send_as_user_and_wait_reply(
    command: str,
    *,
    chat_id: str | None = None,
    timeout: float = 120.0,
    app_id: str | None = None,
    app_secret: str | None = None,
) -> Optional[str]:
    """
    以【用户身份】向飞书群发指令，然后等待 OpenClaw 机器人的回复。

    相比 send_command_and_wait_reply（机器人身份），
    用户身份发的消息可以正常触发 OpenClaw 等机器人响应。

    首次调用会打开浏览器要求飞书登录授权，之后自动使用缓存 token。
    """
    _app_id = app_id or FEISHU_APP_ID
    _app_secret = app_secret or FEISHU_APP_SECRET
    _chat_id = chat_id or FEISHU_TARGET_CHAT_ID

    # 先启动监听，再发消息
    waiter = FeishuReplyWaiter(
        app_id=_app_id,
        app_secret=_app_secret,
        target_chat_id=_chat_id,
    )
    waiter.start()

    try:
        user_auth = FeishuUserAuth(app_id=_app_id, app_secret=_app_secret)
        sent_at = time.time()
        user_auth.send_text_as_user(chat_id=_chat_id, text=command)
        print(f"[openclaw] 已以用户身份发送指令：{command!r}")
        print(f"[openclaw] 等待 OpenClaw 回复（最多 {timeout} 秒）...")

        reply = waiter.wait(sent_at=sent_at, timeout=timeout)
        if reply is None:
            print(f"[openclaw] 超时（{timeout}s），未收到回复。")
        else:
            print(f"[openclaw] 收到回复（{len(reply)} 字）。")
        return reply
    finally:
        waiter.stop()


# ──────────────────────────────────────────
class FeishuReplyWaiter:
    """
    用 lark-oapi 的 WebSocket 客户端监听飞书事件流。

    工作流程：
    1. 建立 WebSocket 长连接（飞书主动推送事件）；
    2. 发送消息后记录 sent_at 时间戳；
    3. 收到 im.message.receive_v1 事件，满足以下条件时认为是机器人回复：
       - 消息所在群 == target_chat_id
       - sender_type == "app"（排除真人用户消息）
       - 消息创建时间 >= sent_at（排除历史消息）
    4. 提取消息文本，写入 _result，触发 Event，主线程解除阻塞。
    """

    def __init__(self, app_id: str, app_secret: str, target_chat_id: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.target_chat_id = target_chat_id
        self._result: Optional[str] = None
        self._event = threading.Event()
        self._sent_at: float = 0.0
        self._ws_client: Optional[lark.ws.Client] = None
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _extract_text(msg: Any) -> str:
        """从飞书消息对象中提取纯文本。"""
        try:
            msg_type = msg.msg_type
            raw = msg.body.content  # JSON 字符串
            content = json.loads(raw)
            if msg_type == "text":
                # OpenClaw 回复通常是 text，内容在 content["text"]
                return content.get("text", "")
            if msg_type in ("post", "markdown"):
                zh = content.get("zh_cn") or content.get("en_us") or {}
                parts = []
                for line in zh.get("content", []):
                    for seg in line:
                        if seg.get("tag") == "text":
                            parts.append(seg.get("text", ""))
                return "\n".join(parts)
            return raw
        except Exception:
            return str(msg)

    def _on_message(self, data: P2ImMessageReceiveV1) -> None:
        """飞书推送的 im.message.receive_v1 事件回调。"""
        if self._event.is_set():
            return
        try:
            msg = data.event.message
            sender = data.event.sender

            # 必须是目标群
            if msg.chat_id != self.target_chat_id:
                return

            # 只接受 app（机器人）发的消息，忽略真人
            sender_type = getattr(sender, "sender_type", None)
            if sender_type == "user":
                return

            # 消息时间必须晚于我们发送的时刻（避免读到历史消息）
            create_time_ms = int(getattr(msg, "create_time", "0") or "0")
            if create_time_ms / 1000.0 < self._sent_at - 2:
                return

            text = self._extract_text(msg)
            if text:
                self._result = text
                self._event.set()
        except Exception as e:
            print(f"[FeishuReplyWaiter] 事件处理异常：{e}")

    def start(self) -> None:
        """在后台守护线程启动 WebSocket 监听。"""
        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )
        ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.ERROR,
        )
        self._ws_client = ws_client
        self._thread = threading.Thread(target=ws_client.start, daemon=True)
        self._thread.start()
        # 等待 WebSocket 完成握手
        time.sleep(2.0)
        print("[FeishuReplyWaiter] WebSocket 已连接，开始监听事件...")

    def wait(self, sent_at: float, timeout: float = 60.0) -> Optional[str]:
        """
        设置发送时刻，阻塞等待机器人回复。

        参数：
        - sent_at: 发送消息时的 time.time() 时间戳
        - timeout: 最长等待秒数

        返回：回复文本；超时返回 None。
        """
        self._sent_at = sent_at
        self._event.wait(timeout=timeout)
        return self._result

    def stop(self) -> None:
        """停止 WebSocket 连接。"""
        try:
            if self._ws_client:
                self._ws_client.stop()
        except Exception:
            pass


# ──────────────────────────────────────────
# 核心：只监听，不发消息
# ──────────────────────────────────────────
def wait_for_openclaw_reply(
    *,
    chat_id: str | None = None,
    timeout: float = 120.0,
    app_id: str | None = None,
    app_secret: str | None = None,
) -> Optional[str]:
    """
    监听飞书群，等待 OpenClaw 机器人的回复，返回回复文本。

    本函数【不发送任何消息】，只负责监听。
    指令由用户或其他机器人在飞书群里发送，OpenClaw 收到后会回复，
    本函数捕获该回复并返回。

    典型用法：
        # 1. 先在飞书群发指令（由人或其他程序完成）
        # 2. 调用本函数等待 OpenClaw 的回复
        reply = wait_for_openclaw_reply(timeout=60)
        print(reply)

    参数：
    - chat_id    : 目标群聊 chat_id（默认读 config.FEISHU_TARGET_CHAT_ID）
    - timeout    : 最长等待秒数（默认 120 秒）
    - app_id     : 飞书应用 App ID（默认读 config.FEISHU_APP_ID）
    - app_secret : 飞书应用 App Secret（默认读 config.FEISHU_APP_SECRET）

    返回：OpenClaw 机器人回复的纯文本；超时返回 None。
    """
    _app_id = app_id or FEISHU_APP_ID
    _app_secret = app_secret or FEISHU_APP_SECRET
    _chat_id = chat_id or FEISHU_TARGET_CHAT_ID

    if not _app_id or not _app_secret:
        raise ValueError("请先在 config.py 中设置 FEISHU_APP_ID 与 FEISHU_APP_SECRET。")
    if not _chat_id:
        raise ValueError("请先在 config.py 中设置 FEISHU_TARGET_CHAT_ID。")

    waiter = FeishuReplyWaiter(
        app_id=_app_id,
        app_secret=_app_secret,
        target_chat_id=_chat_id,
    )
    waiter.start()
    listen_start = time.time()
    print(f"[openclaw] 正在监听群 {_chat_id}，等待 OpenClaw 机器人回复（最多 {timeout} 秒）...")

    try:
        reply = waiter.wait(sent_at=listen_start, timeout=timeout)
        if reply is None:
            print(f"[openclaw] 超时（{timeout}s），未收到机器人回复。")
        else:
            print(f"[openclaw] 收到 OpenClaw 回复（{len(reply)} 字）。")
        return reply
    finally:
        waiter.stop()


# ──────────────────────────────────────────
# 扩展：我们的程序主动发指令并等回复
# （适合全自动流程，无需人工介入）
# ──────────────────────────────────────────
def send_command_and_wait_reply(
    command: str,
    *,
    chat_id: str | None = None,
    timeout: float = 120.0,
    app_id: str | None = None,
    app_secret: str | None = None,
    base_url: str | None = None,
) -> Optional[str]:
    """
    由我们的程序主动向飞书群发送一条指令，然后等待 OpenClaw 机器人的回复。

    适合全自动场景（无需人工在飞书手动发消息）。

    参数：
    - command    : 要发给 OpenClaw 的指令文本
    - chat_id    : 目标群聊 chat_id（默认读 config.FEISHU_TARGET_CHAT_ID）
    - timeout    : 最长等待秒数（默认 120 秒）
    - app_id     : 飞书应用 App ID
    - app_secret : 飞书应用 App Secret
    - base_url   : 飞书 API base URL

    返回：OpenClaw 机器人回复的纯文本；超时返回 None。
    """
    _app_id = app_id or FEISHU_APP_ID
    _app_secret = app_secret or FEISHU_APP_SECRET
    _chat_id = chat_id or FEISHU_TARGET_CHAT_ID

    if not _app_id or not _app_secret:
        raise ValueError("请先在 config.py 中设置 FEISHU_APP_ID 与 FEISHU_APP_SECRET。")
    if not _chat_id:
        raise ValueError("请先在 config.py 中设置 FEISHU_TARGET_CHAT_ID。")

    # 先启动监听，再发消息，确保不漏掉快速回复
    waiter = FeishuReplyWaiter(
        app_id=_app_id,
        app_secret=_app_secret,
        target_chat_id=_chat_id,
    )
    waiter.start()

    try:
        feishu = FeishuClient(app_id=_app_id, app_secret=_app_secret, base_url=base_url)
        sent_at = time.time()
        feishu.send_text_to_chat(
            chat_id=_chat_id,
            text=command,
            mention_user_id=OPENCLAW_BOT_OPEN_ID or None,
        )
        print(f"[openclaw] 指令已发送：{command!r}")
        print(f"[openclaw] 等待 OpenClaw 机器人回复（最多 {timeout} 秒）...")

        reply = waiter.wait(sent_at=sent_at, timeout=timeout)
        if reply is None:
            print(f"[openclaw] 超时（{timeout}s），未收到机器人回复。")
        else:
            print(f"[openclaw] 收到回复（{len(reply)} 字）。")
        return reply
    finally:
        waiter.stop()


# ──────────────────────────────────────────
# 直接运行时的简单测试
# ──────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    from config import TEST_TASK_TEXT

    parser = argparse.ArgumentParser(description="OpenClaw 飞书通道测试")
    parser.add_argument(
        "--mode",
        choices=["listen", "send"],
        default="send",
        help=(
            "listen（默认）：只监听，等待用户/其他机器人在飞书发指令后捕获 OpenClaw 的回复；\n"
            "send：由本程序主动发送 TEST_TASK_TEXT 并等待回复。"
        ),
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="等待超时秒数（默认 60）")
    args = parser.parse_args()

    # 配置检查
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET or not FEISHU_TARGET_CHAT_ID:
        print("飞书配置不完整（config.py），请检查 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_TARGET_CHAT_ID。")
        sys.exit(1)

    print(f"目标群  : {FEISHU_TARGET_CHAT_ID}")
    print(f"发送指令: {TEST_TASK_TEXT}")
    print(f"等待超时: {args.timeout} 秒\n")

    if args.mode == "listen":
        print("[提示] 请在飞书群里手动发指令给 OpenClaw，本程序捕获其回复。")
        reply = wait_for_openclaw_reply(timeout=args.timeout)
    else:
        # 以用户身份发送（首次会打开浏览器授权）
        reply = send_as_user_and_wait_reply(TEST_TASK_TEXT, timeout=args.timeout)

    if reply:
        print(f"\nOpenClaw 回复：\n{reply}")
    else:
        print("\n未收到 OpenClaw 回复（超时或配置问题）。")