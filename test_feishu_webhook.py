#!/usr/bin/env python3
"""
飞书 Webhook 测试程序

用途：
1. 测试 URL 校验（challenge）请求是否正确处理
2. 测试消息事件是否能正确解析并写入全局 store

用法：
  # 方式一：模拟发送 challenge 请求到主应用（需先启动 web 服务）
  python test_feishu_webhook.py --challenge

  # 方式二：启动独立测试服务器，接收真实飞书回调（需公网可访问，如配合 ngrok）
  python test_feishu_webhook.py --serve [--port 8765]

  # 方式三：模拟完整消息事件，验证 handler 逻辑
  python test_feishu_webhook.py --simulate-message
"""
import argparse
import json
import sys
from pathlib import Path

# 确保项目根目录在 path 中
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_challenge():
    """模拟飞书 URL 校验请求，发送到本地 /api/feishu/event。"""
    import urllib.request
    challenge_val = "test_challenge_12345"
    payload = json.dumps({
        "challenge": challenge_val,
        "type": "url_verification",
        "token": "test_token",
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/feishu/event",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
            if data.get("challenge") == challenge_val:
                print("✅ URL 校验测试通过：正确返回了 challenge")
                return 0
            print(f"❌ 返回 body 不符合预期: {body}")
            return 1
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP 错误 {e.code}: {e.read().decode()}")
        return 1
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        print("提示：请先启动 web 服务：cd web && uvicorn app:app --host 0.0.0.0 --port 8000")
        return 1


def test_simulate_message():
    """模拟 im.message.receive_v1 事件，验证 handler 能否解析并写入 store。"""
    from config import FEISHU_TARGET_CHAT_ID
    from openclaw import _feishu_chat_replies, _feishu_replies_lock, get_feishu_event_handler

    # 模拟飞书 2.0 消息事件（使用 config 中的 FEISHU_TARGET_CHAT_ID）
    payload = {
        "schema": "2.0",
        "header": {
            "event_id": "test_event_001",
            "event_type": "im.message.receive_v1",
            "create_time": "1608725989000",
            "token": "",
            "app_id": "cli_test",
            "tenant_key": "tenant_test",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_test_user"},
                "sender_type": "user",
                "tenant_key": "tenant_test",
            },
            "message": {
                "message_id": "om_test_001",
                "chat_id": FEISHU_TARGET_CHAT_ID,
                "create_time": "1731750000000",  # 未来时间戳
                "content": json.dumps({"text": "这是一条测试消息，来自模拟飞书事件"}),
            },
        },
    }
    body = json.dumps(payload).encode("utf-8")
    # 使用 do_without_validation 跳过 token 校验，便于本地测试
    handler = get_feishu_event_handler()
    handler.do_without_validation(body)
    print("Handler 已处理模拟事件（do_without_validation）")

    with _feishu_replies_lock:
        replies = _feishu_chat_replies.get(FEISHU_TARGET_CHAT_ID, [])
    if replies:
        ts, text = replies[-1]
        print(f"✅ 模拟消息已写入 store: chat_id={FEISHU_TARGET_CHAT_ID}")
        print(f"   最新消息: [{ts}] {text[:80]}...")
        return 0
    print("⚠️ store 中未见新消息，请检查 handler 逻辑")
    return 0


def serve_standalone(port: int = 8765):
    """启动独立 HTTP 服务器，仅用于接收飞书 webhook 回调测试。"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from openclaw import get_feishu_event_handler
    from lark_oapi.core.model import RawRequest

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/api/feishu/event" and self.path != "/event":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            req = RawRequest()
            req.uri = self.path
            req.body = body
            req.headers = dict(self.headers)
            try:
                evt_handler = get_feishu_event_handler()
                resp = evt_handler.do(req)
                out = resp.content or b"{}"
                self.send_response(resp.status_code or 200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(out)
                print(f"[webhook] 收到请求 {len(body)} 字节, 返回 {resp.status_code}")
            except Exception as e:
                print(f"[webhook] 处理异常: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        def log_message(self, fmt, *args):
            print(f"[http] {args[0]}")

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"飞书 Webhook 测试服务已启动: http://0.0.0.0:{port}/api/feishu/event")
    print("在飞书开发者后台将请求地址设为: http://你的公网IP或域名:{port}/api/feishu/event")
    print("或配合 ngrok: ngrok http {port}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description="飞书 Webhook 测试")
    parser.add_argument("--challenge", action="store_true", help="模拟 URL 校验请求，测试主应用")
    parser.add_argument("--simulate-message", action="store_true", help="模拟消息事件，验证 handler")
    parser.add_argument("--serve", action="store_true", help="启动独立测试服务器")
    parser.add_argument("--port", type=int, default=8765, help="--serve 时的端口")
    args = parser.parse_args()

    if args.serve:
        serve_standalone(args.port)
        return

    if args.challenge:
        sys.exit(test_challenge())

    if args.simulate_message:
        sys.exit(test_simulate_message())

    parser.print_help()
    print("\n示例:")
    print("  python test_feishu_webhook.py --challenge          # 测试 URL 校验（需先启动 web）")
    print("  python test_feishu_webhook.py --simulate-message # 模拟消息事件")
    print("  python test_feishu_webhook.py --serve --port 8765 # 独立测试服务器")


if __name__ == "__main__":
    main()
