#!/usr/bin/env python3
"""
测试以飞书用户身份发消息，并可选等待机器人回复。

用法：
    # 发到群聊（默认 FEISHU_TARGET_CHAT_ID）
    python3 test_feishu_send.py

    # 发到机器人私聊（使用 OPENCLAW_P2P_CHAT_ID 或 OPENCLAW_BOT_OPEN_ID）
    python3 test_feishu_send.py --p2p

    # 自定义消息
    python3 test_feishu_send.py --p2p "ping: 请回复 ok"

    # 只发送，不等待回复
    python3 test_feishu_send.py --p2p --no-wait

首次运行会打开浏览器完成飞书 OAuth 授权。
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_TARGET_CHAT_ID,
    OPENCLAW_BOT_OPEN_ID,
    OPENCLAW_P2P_CHAT_ID,
    OPENCLAW_BOT_APP_ID,
)
from openclaw import FeishuUserAuth, FeishuReplyWaiter

DEFAULT_MSG = "ping: 请回复 ok，并说明你当前可用的模型提供方。"


def run(
    msg: str,
    p2p: bool = False,
    p2p_chat_id: str | None = None,
    no_wait: bool = False,
    timeout: float = 60.0,
) -> None:
    auth = FeishuUserAuth(app_id=FEISHU_APP_ID, app_secret=FEISHU_APP_SECRET)

    # 确定发送目标
    if p2p:
        chat_id = p2p_chat_id or OPENCLAW_P2P_CHAT_ID or ""
        if chat_id and chat_id.strip():
            receive_id = chat_id.strip()
            receive_id_type = "chat_id"
        elif OPENCLAW_BOT_OPEN_ID:
            receive_id = OPENCLAW_BOT_OPEN_ID
            receive_id_type = "open_id"
        else:
            print("[✗] P2P 模式需要配置 OPENCLAW_P2P_CHAT_ID 或 OPENCLAW_BOT_OPEN_ID")
            sys.exit(1)
    else:
        receive_id = FEISHU_TARGET_CHAT_ID
        receive_id_type = "chat_id"

    waiter = None
    if not no_wait and receive_id_type == "chat_id":
        waiter = FeishuReplyWaiter(
            app_id=FEISHU_APP_ID,
            app_secret=FEISHU_APP_SECRET,
            target_chat_id=receive_id,
            exclude_app_id=FEISHU_APP_ID,
        )
        waiter.start()

    try:
        auth.send_text_as_user(
            receive_id=receive_id,
            text=msg,
            receive_id_type=receive_id_type,
        )
        print(f"[✓] 已发送：{msg!r}")

        if no_wait:
            return
        if receive_id_type != "chat_id":
            print("[!] open_id 模式无法等待回复（需 chat_id）")
            return
        import time
        sent_at = time.time()
        reply = waiter.wait(sent_at=sent_at, timeout=timeout)
        if reply:
            print(f"[✓] 收到回复（{len(reply)} 字）：{reply[:200]}...")
        else:
            print("[!] 超时，未收到回复")
    finally:
        if waiter:
            waiter.stop()


def main() -> None:
    ap = argparse.ArgumentParser(description="以用户身份向飞书发消息")
    ap.add_argument("msg", nargs="?", default=DEFAULT_MSG, help="消息内容")
    ap.add_argument("--p2p", action="store_true", help="发到机器人私聊")
    ap.add_argument("--p2p-chat-id", metavar="ID", help="P2P 会话 chat_id，覆盖 config")
    ap.add_argument("--no-wait", action="store_true", help="只发送，不等待回复")
    ap.add_argument("--timeout", type=float, default=60, help="等待回复超时（秒）")
    args = ap.parse_args()
    run(
        msg=args.msg,
        p2p=args.p2p,
        p2p_chat_id=args.p2p_chat_id,
        no_wait=args.no_wait,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
