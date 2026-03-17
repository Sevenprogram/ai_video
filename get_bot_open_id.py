#!/usr/bin/env python3
"""
获取飞书机器人的 open_id

用途：私聊指定机器人时需要其 open_id，填入 config.py 的 OPENCLAW_BOT_OPEN_ID。

注意：飞书「获取群成员列表」API 可能不返回群内机器人，若本脚本未列出目标机器人，
      可尝试：1) 飞书开放平台 → 对应应用 → 成员与权限；2) 在 API 调试台搜索复制。

用法：
    # 使用 config 中的默认群聊
    python3 get_bot_open_id.py

    # 指定群聊 chat_id
    python3 get_bot_open_id.py oc_xxxx
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_TARGET_CHAT_ID
from openclaw import FeishuClient


def main() -> None:
    chat_id = sys.argv[1] if len(sys.argv) > 1 else FEISHU_TARGET_CHAT_ID

    print(f"正在获取群聊 {chat_id} 的成员列表（含机器人）...")
    print("-" * 60)

    client = FeishuClient(app_id=FEISHU_APP_ID, app_secret=FEISHU_APP_SECRET)
    members = client.list_chat_members(chat_id)

    # 按类型分组：机器人 vs 用户
    bots = []
    users = []
    for m in members:
        mid = m.get("member_id", "")
        mtype = m.get("member_id_type", "")
        name = m.get("name", "(未命名)")
        if mtype == "open_id":
            # 机器人通常以 app 身份加入，或通过 member_id 判断
            # 飞书 API 返回中，机器人的 member_id_type 可能为 open_id，需结合 name 判断
            if "机器人" in name or "bot" in name.lower() or "Bot" in name:
                bots.append((mid, name))
            else:
                users.append((mid, name))
        else:
            users.append((mid, name))

    print("【机器人 / Bot】（open_id 用于私聊）")
    print("-" * 60)
    if bots:
        for oid, name in bots:
            print(f"  open_id: {oid}")
            print(f"  名称:   {name}")
            print()
    else:
        print("  （未找到明显标记为机器人的成员，以下列出 member_id_type=open_id 的成员）")
        print()

    print("【所有成员（open_id 类型）】")
    print("-" * 60)
    for m in members:
        if m.get("member_id_type") == "open_id":
            mid = m.get("member_id", "")
            name = m.get("name", "(未命名)")
            print(f"  {mid}  —  {name}")

    print()
    print("将目标机器人的 open_id 填入 config.py 的 OPENCLAW_BOT_OPEN_ID，即可私聊。")


if __name__ == "__main__":
    main()
