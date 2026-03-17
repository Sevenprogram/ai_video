"""
主流程：分镜生成、录屏指令构建、与 OpenClaw 交互。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import VIDEO_DURATION_MINUTES


# ──────────────────────────────────────────
# 分镜提示词
# ──────────────────────────────────────────
def build_storyboard_prompt(script: str) -> str:
    """
    根据文稿生成分镜提示词，供 LLM 产出 JSON 格式的分镜列表。
    """
    minutes = VIDEO_DURATION_MINUTES
    return f"""请根据以下视频文稿，生成浏览器录屏分镜的 JSON 列表。每个分镜需要指定：
- id: 序号（从 1 开始）
- start_sec, end_sec, duration_sec: 时间轴
- page_type: 页面类型（如 social/chart/dashboard）
- source: 来源（如 twitter/coinglass/ezpro）
- url: 要打开的完整 URL
- view: 聚焦区域名称（如 main_feed, btc_liquidation_heatmap）
- scroll_behavior: none | scroll_down_slow | scroll_up_slow
- action: static_view | hover_on_xxx | 等操作描述
- text_clip: 该分镜对应的台词（可截断）
- notes: 中文备注，描述该镜头要展示的内容

目标总时长约 {minutes} 分钟。分镜数量建议 8-15 个，每个分镜 3-15 秒。
返回格式为 JSON，包含 "shots" 数组，例如：
{{"shots": [{{"id": 1, "start_sec": 0, "end_sec": 5.5, "duration_sec": 5.5, "url": "...", ...}}, ...]}}

文稿：
---
{script}
---
请只输出 JSON，不要输出其他文字。"""


# ──────────────────────────────────────────
# 录屏指令
# ──────────────────────────────────────────
def _action_to_page_op(shot: dict) -> tuple:
    """将 shot 的 action/scroll_behavior 映射为页面操作描述和 emoji。"""
    action = shot.get("action", "static_view") or "static_view"
    scroll = shot.get("scroll_behavior", "none") or "none"
    if "scroll" in str(action).lower() or scroll in ("scroll_down_slow", "scroll_up_slow"):
        return ("📜", "缓慢向下滚动页面" if "down" in scroll else "缓慢向上滚动页面")
    if "hover" in str(action).lower():
        return ("🖱", "鼠标缓慢悬停在高爆仓区域" if "liquidation" in str(action).lower() else "鼠标悬停")
    if "click" in str(action).lower():
        return ("🖱", "点击页面刷新按钮")
    return ("📌", "固定展示，保持静止 {:.1f} 秒".format(shot.get("duration_sec", 5)))


def build_recording_instruction(shots: list, folder_name: str) -> str:
    """
    根据分镜列表生成发给 OpenClaw 的录屏指令文本。
    包含「请调用 parallel-web-recorder 这个 skill」及「请直接进行录屏，不需要提问」。
    """
    if not shots:
        return ""
    total_sec = sum(s.get("duration_sec", 0) for s in shots)
    lines = [
        f"【录屏任务】{folder_name}",
        f"📋 总时长：约 {int(total_sec)} 秒 | 分镜数：{len(shots)} 个",
        "",
        "✅ 请调用 parallel-web-recorder 这个 skill 完成录屏任务。",
        "",
        "⚠️  操作说明：",
        "1. 开始前先开启录屏软件，录制整个屏幕。",
        "2. 按下方分镜顺序依次操作，每个分镜在对应页面停留指定时长。",
        "3. 所有分镜操作完成后停止录屏，将视频保存到本地。",
        "4. 完成后回复：完成",
        "=" * 50,
        "",
    ]
    for i, s in enumerate(shots):
        idx = i + 1
        dur = s.get("duration_sec", 5)
        start = s.get("start_sec", 0)
        end = s.get("end_sec", start + dur)
        url = s.get("url", "")
        view = s.get("view", "")
        emoji, op_desc = _action_to_page_op(s)
        text_clip = (s.get("text_clip") or "")[:80] + ("..." if len(s.get("text_clip") or "") > 80 else "")
        notes = s.get("notes", "")
        block = [
            f"── 分镜 {idx}/{len(shots)} ──────────────────────",
            f"⏱  停留时长：{dur:.1f} 秒（视频时间轴：{start:.1f}s - {end:.1f}s）",
            f"🌐 打开页面：{url}",
        ]
        if view:
            block.append(f"🔍 聚焦区域：{view}（将该区域置于屏幕中央）")
        block.append(f"{emoji}  页面操作：{op_desc}")
        if text_clip:
            block.append(f"🎤 同步台词：{text_clip}")
        if notes:
            block.append(f"📝 备注：{notes}")
        block.append("")
        lines.extend(block)
    lines.extend([
        "=" * 50,
        f"✅ 以上共 {len(shots)} 个分镜，合计约 {int(total_sec)} 秒。",
        "✅ 请全程保持录屏，操作完所有分镜后停止录制，保存为一个完整视频文件。",
        "✅ 完成后请回复：完成",
        "",
        "请直接进行录屏，不需要提问任何的其他问题！请直接按照要求进行录屏，不需要提问任何的其他问题！",
    ])
    return "\n".join(lines)
