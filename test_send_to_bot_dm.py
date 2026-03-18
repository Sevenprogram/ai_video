#!/usr/bin/env python3
"""
测试：直接通过「OpenClaw 机器人」私聊发送指令（不通过飞书群组）

图中所示是与 openclaw 机器人的 1-on-1 聊天框（带「机器人」标签）。
本脚本验证：以用户身份向该私聊会话发消息，并能否收到机器人回复。

用法：
  # 1. 获取「机器人私聊」的 chat_id（只需做一次）
  python test_send_to_bot_dm.py --listen-chat-id
  # 启动后，在飞书里打开与 openclaw 的私聊，发任意一条消息；
  # 控制台会打印该会话的 chat_id，填入 config.py 的 FEISHU_BOT_CHAT_ID

  # 2. 使用 config 中的 FEISHU_BOT_CHAT_ID 发送测试指令
  python test_send_to_bot_dm.py

  # 3. 指定私聊 chat_id 发送（覆盖 config）
  python test_send_to_bot_dm.py --chat-id oc_xxxxxxxx

  # 4. 自定义测试文案
  python test_send_to_bot_dm.py --text "什么进度了?"
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def listen_chat_id(port: int = 8766):
    """启动临时 HTTP 服务，接收飞书回调，打印收到消息的 chat_id，便于用户获取「机器人私聊」的 chat_id。"""
    from http.server import HTTPServer, BaseHTTPRequestHandler

    chat_ids_seen = set()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/api/feishu/event" and self.path != "/event":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()

            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                self.wfile.write(b"{}")
                return

            # 飞书 URL 校验
            if data.get("type") == "url_verification":
                self.wfile.write(json.dumps({"challenge": data.get("challenge", "")}).encode("utf-8"))
                return

            # 消息事件：提取 chat_id
            event = data.get("event") or data.get("event", {})
            msg = event.get("message") if isinstance(event, dict) else getattr(event, "message", None)
            if msg is None:
                self.wfile.write(b"{}")
                return
            if isinstance(msg, dict):
                chat_id = msg.get("chat_id") or msg.get("chat_id", "")
            else:
                chat_id = getattr(msg, "chat_id", None) or ""

            if chat_id and chat_id not in chat_ids_seen:
                chat_ids_seen.add(chat_id)
                print(f"\n>>> 收到会话 chat_id: {chat_id}")
                print("    请将此值填入 config.py 的 FEISHU_BOT_CHAT_ID，即可通过机器人私聊发送指令。\n")

            # 交给项目原有 handler 处理（若存在），避免校验失败
            try:
                from openclaw import get_feishu_event_handler
                handler = get_feishu_event_handler()
                handler.do_without_validation(body)
            except Exception:
                pass
            self.wfile.write(b"{}")

        def log_message(self, fmt, *args):
            pass

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"监听 chat_id 服务已启动: http://0.0.0.0:{port}/api/feishu/event")
    print("请在飞书开发者后台将「事件订阅」请求地址临时改为: http://你的公网IP或域名:{port}/api/feishu/event")
    print("然后在飞书里打开与 openclaw 机器人的私聊，发送任意一条消息。")
    print("按 Ctrl+C 结束。\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(
        description="测试通过 OpenClaw 机器人私聊发送指令（不通过群组）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--chat-id",
        type=str,
        default=None,
        help="机器人私聊的 chat_id，不填则使用 config 中 FEISHU_BOT_CHAT_ID 或 FEISHU_TARGET_CHAT_ID",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="要发送的测试文案，默认使用 config 中 TEST_TASK_TEXT",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="等待机器人回复的超时秒数（默认 90）",
    )
    parser.add_argument(
        "--use-bot",
        action="store_true",
        help="以机器人身份发送消息（适用于私聊，需用户已与机器人开启会话）",
    )
    parser.add_argument(
        "--listen-chat-id",
        action="store_true",
        help="启动临时服务，接收飞书回调并打印 chat_id，用于获取「机器人私聊」的 chat_id",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8766,
        help="--listen-chat-id 时使用的端口（默认 8766）",
    )
    args = parser.parse_args()

    if args.listen_chat_id:
        listen_chat_id(port=args.port)
        return 0

    from config import (
        FEISHU_APP_ID,
        FEISHU_APP_SECRET,
        FEISHU_TARGET_CHAT_ID,
        FEISHU_BOT_CHAT_ID,
        TEST_TASK_TEXT,
    )
    from openclaw import send_as_user_and_wait_reply, FeishuUserAuth

    chat_id = args.chat_id or FEISHU_BOT_CHAT_ID or FEISHU_TARGET_CHAT_ID
    text = args.text or TEST_TASK_TEXT
    use_bot = args.use_bot

    if not (args.chat_id or FEISHU_BOT_CHAT_ID):
        print("[提示] 未配置 FEISHU_BOT_CHAT_ID，当前使用群聊 chat_id。")
        print("       若要通过机器人私聊测试，请先运行: python test_send_to_bot_dm.py --listen-chat-id")
        print("       获取私聊 chat_id 后填入 config.py 的 FEISHU_BOT_CHAT_ID。\n")

    # 如果传入的是用户的 open_id (ou_xxx)，先获取对应的私聊 chat_id
    actual_chat_id = chat_id
    if chat_id.startswith("ou_"):
        print(f"[转换] 用户的 open_id={chat_id}，正在获取对应的私聊 chat_id...\n")
        try:
            from openclaw import FeishuClient
            client = FeishuClient(FEISHU_APP_ID, FEISHU_APP_SECRET)
            actual_chat_id = client.get_or_create_p2p_chat(chat_id)
            print(f"[成功] 私聊 chat_id: {actual_chat_id}\n")
        except Exception as e:
            print(f"[警告] 获取私聊 chat_id 失败: {e}")
            print("    尝试直接使用 open_id 发送...\n")

    # 如果使用 --use-bot，使用机器人身份发送
    if use_bot:
        print("[模式] 以机器人身份发送消息...\n")
        try:
            from openclaw import FeishuUserAuth
            auth = FeishuUserAuth(FEISHU_APP_ID, FEISHU_APP_SECRET)
            result = auth.send_text_as_bot(actual_chat_id, text)
            print(f"[发送成功] message_id: {result.get('data', {}).get('message_id')}")
            print("（注意：以机器人身份发送时，机器人回复不会自动写入 store，若需等待回复请使用用户身份发送）")
            return 0
        except Exception as e:
            print(f"机器人身份发送失败: {e}")
            return 1

    print(f"[发送] chat_id={chat_id}")
    print(f"[发送] 内容: {text[:80]}{'...' if len(text) > 80 else ''}\n")

    try:
        reply = send_as_user_and_wait_reply(
            text,
            chat_id=chat_id,
            timeout=args.timeout,
            wait=True,
        )
        if reply:
            print("[回复] 收到 OpenClaw 回复:")
            print("-" * 40)
            print(reply)
            print("-" * 40)
            print("✅ 通过当前会话（群聊或机器人私聊）发送并收到回复成功。")
        else:
            print("⚠️ 未在超时内收到回复，请检查：")
            print("   1. 飞书事件订阅请求地址是否可达、是否已校验通过")
            print("   2. 若使用机器人私聊，FEISHU_BOT_CHAT_ID 是否为该私聊的 chat_id")
        return 0 if reply else 1
    except Exception as e:
        print(f"❌ 发送或等待回复失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
