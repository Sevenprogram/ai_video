#!/usr/bin/env python3
"""
创建与目标机器人的 P2P 会话，并输出 chat_id。

用于解决 open_id cross app（99992361）错误：当目标机器人属于其他应用时，
用 open_id 私聊会失败，改用 chat_id 即可。

用法：
    # 使用 config 中的 OPENCLAW_BOT_APP_ID
    python3 get_p2p_chat_id.py

    # 指定机器人 app_id
    python3 get_p2p_chat_id.py cli_xxxx

前置：config.py 中需设置 OPENCLAW_BOT_APP_ID（目标机器人的 app_id，格式 cli_xxx）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, OPENCLAW_BOT_APP_ID
from openclaw import FeishuUserAuth, FeishuClient


def main() -> None:
    bot_app_id = sys.argv[1] if len(sys.argv) > 1 else OPENCLAW_BOT_APP_ID
    if not bot_app_id or not bot_app_id.startswith("cli_"):
        print("[✗] 请提供机器人 app_id（格式 cli_xxx）")
        print("    方式 1：在 config.py 设置 OPENCLAW_BOT_APP_ID")
        print("    方式 2：python3 get_p2p_chat_id.py cli_xxxx")
        sys.exit(1)

    print("正在获取当前用户信息...")
    auth = FeishuUserAuth(app_id=FEISHU_APP_ID, app_secret=FEISHU_APP_SECRET)
    user_info = auth.get_user_info()
    user_open_id = user_info.get("open_id") or user_info.get("user_id")
    if not user_open_id:
        print(f"[✗] 无法获取 open_id，user_info: {user_info}")
        sys.exit(1)
    print(f"  当前用户 open_id: {user_open_id}")

    print(f"正在创建与机器人 {bot_app_id} 的 P2P 会话...")
    client = FeishuClient(app_id=FEISHU_APP_ID, app_secret=FEISHU_APP_SECRET)
    try:
        chat_id = client.create_p2p_chat(user_open_id=user_open_id, bot_app_id=bot_app_id)
    except Exception as e:
        print(f"[✗] 创建失败：{e}")
        sys.exit(1)

    print()
    print("=" * 55)
    print("P2P chat_id 已创建。将其填入 config.py 的 OPENCLAW_P2P_CHAT_ID 后，")
    print("可直接运行：python3 test_feishu_send.py --p2p \"消息\"（无需再授权）")
    print()
    print(f"  OPENCLAW_P2P_CHAT_ID = \"{chat_id}\"")
    print()
    print("或临时指定：")
    print(f"  python3 test_feishu_send.py --p2p-chat-id {chat_id} \"ping\"")
    print("=" * 55)


if __name__ == "__main__":
    main()
