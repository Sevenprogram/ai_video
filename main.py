import os
import sys
import json
from datetime import datetime
from typing import Callable, List, Optional

from module import gemini_complete, text_to_speech_to_file
from openclaw import send_as_user_and_wait_reply
from config import VIDEO_DURATION_MINUTES

# video_module 目录（pipeline / synthesis 都在这里）
_VIDEO_MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_module")
if _VIDEO_MODULE_DIR not in sys.path:
    sys.path.insert(0, _VIDEO_MODULE_DIR)

# video_module 内的固定子目录
_ACTION_CLIPS_DIR = os.path.join(_VIDEO_MODULE_DIR, "action_clips")
_VIDEO_SHOOT_DIR  = os.path.join(_VIDEO_MODULE_DIR, "video_shoot")


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def log(message: str) -> None:
    """CLI 时间戳日志。"""
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {message}")


DEFAULT_PROMPT = """\
---
✍️ ElevenLabs 专用：全场景工业级文稿设计提示词
Role: 你是一位顶级短视频编剧和 AI 导演，擅长设计具备极致真人感、且为数字人动作预留精准物理空间的"全场景导演剧本"。
Task: 1. 请分析 Ezpro.club 网站的核心功能（重点关注 15-win 挑战、Signal-Free 模式、裸 K 线交易环境）。 2. 实时抓取并分析过去 24 小时内 Twitter/X 或 YouTube 上关于加密货币的热点（如：特定品种的巨额清算、大 V 观点冲突、或类似 Brad Trades 的最新带单反馈）。 3. 基于上述热点与网站功能，生成一份模块化视频文稿。文稿必须直接适配 ElevenLabs 的文本解析逻辑，禁止使用不支持的标签。
1. 文稿指令规范 (ElevenLabs Standards):
- 停顿叠加: 严禁使用 SSML 标签。在场景转换处使用 ... [pause]；在需要执行大幅度动作（如喝水、点鼠标）处，强制连续叠加 [silent] [silent] [silent] 以创造 6 秒以上的纯动作窗口。
- 真人杂质: 在文案中随机自然植入情绪标签词，如 [smacks lips]、[chuckles]、[clears throat]、[sighs]。
- 节奏语气: 必须包含口语化的"自我纠正"逻辑，例如使用 Wait...、Actually... 等词汇引导语速自然变化。
2. 模块化内容池 (ABC Logic):
- A 段 (引子): 引用 YouTube 评论、Twitter 大 V (如 Brad Trades) 或清算新闻作为现实锚点。
- B 段 (场景库): 生成 3 段以上可独立组合的内容块：
  - [数据场景]: 解读 CoinGlass 爆仓热力图或费率。
  - [实盘场景]: 分析 Ezpro 裸 K 线 的支撑压力位及 Signal-Free 逻辑。
  - [社交复盘]: 专业反驳或点评某段热门 YouTube 交易视频。
- C 段 (实操): 展示产品操作细节（如刷新页面）并引导加入 Telegram 群组。

请确定你输出的内容是文稿，只需要包括口播的部分，内容需要是英文的，Start directly from the first sentence that would be spoken in the video.
"""


# --------------------------------------------------------------------------- #
# 核心构建函数
# --------------------------------------------------------------------------- #

def build_storyboard_prompt(script: str, duration_minutes: int = VIDEO_DURATION_MINUTES) -> str:
    """根据口播文稿生成分镜提示词。"""
    total_sec = duration_minutes * 60
    return (
        "你是一位资深 AI 视频分镜师，同时也是为 OpenClaw 生成可执行录屏指令的规划师。\n"
        "请根据下面这段口播文稿（含 [pause]/[silent] 标签），输出一组结构化分镜 JSON。\n\n"
        "【时长估算规则】\n"
        "- 每个 [pause] 约 0.5 秒，每个 [silent] 约 2 秒。\n"
        "- 英文正常语速约每分钟 130 词，据此推算各段台词时长。\n"
        f"- 目标总时长约 {duration_minutes} 分钟（{total_sec} 秒），分镜时间戳需覆盖完整时长，不要遗漏。\n\n"
        "【拆分规则】\n"
        "- 按时间顺序拆分为 3-20 个镜头，覆盖完整时长，不要遗漏。\n"
        "- 时间必须单调递增，上一镜头的 end_sec <= 下一镜头的 start_sec。\n\n"
        "【每个镜头字段】\n"
        "- id: int，从 1 开始。\n"
        "- start_sec / end_sec: number，单位秒。\n"
        "- duration_sec: number，等于 end_sec - start_sec。\n"
        "- page_type: 'browser' / 'social' / 'chart' / 'logo'。\n"
        "- source: 站点名，如 'youtube' / 'coinglass' / 'ezpro' / 'tradingview' / 'twitter'。\n"
        "- url: 该镜头需要展示的具体网页地址（尽量给出真实可访问的 URL）。\n"
        "- view: 页面内聚焦区域，如 'comments_section' / 'btc_liquidation_heatmap' / 'live_kline'。\n"
        "- scroll_behavior: 'none' / 'scroll_down_slow' / 'scroll_up_slow' / 'scroll_down_fast'。\n"
        "- action: 'static_view' / 'hover_on_high_liquidation_zones' / 'click_refresh_button' 等。\n"
        "- text_clip: 与该镜头对应的原文台词片段。\n"
        "- notes: 补充说明（可选）。\n"
        "- interaction: 鼠标/键盘交互描述（可选）。\n\n"
        "【输出格式（极其重要）】\n"
        "只输出纯 JSON 数组，不要任何解释、标题、Markdown 或代码块标记。\n\n"
        "文稿如下：\n\n"
        + script
    )


def build_recording_instruction(shots: list, folder_name: str) -> str:
    """将分镜 JSON 列表转换为发给 OpenClaw 的完整录屏指令文本。"""
    total_duration = max((s.get("end_sec", 0) for s in shots), default=0)
    lines = [
        f"【录屏任务】{folder_name}",
        f"📋 总时长：约 {total_duration:.0f} 秒 | 分镜数：{len(shots)} 个",
        "",
        "⚠️  操作说明：",
        "1. 开始前先开启录屏软件，录制整个屏幕。",
        "2. 按下方分镜顺序依次操作，每个分镜在对应页面停留指定时长。",
        "3. 所有分镜操作完成后停止录屏，将视频保存到本地。",
        "4. 完成后回复：完成",
        "=" * 50,
    ]

    action_desc = {
        "none": "固定画面，不做任何操作",
        "scroll_down_slow": "缓慢向下滚动页面",
        "scroll_up_slow": "缓慢向上滚动页面",
        "scroll_down_fast": "较快向下滚动页面",
        "static_view": "固定画面，不做任何操作",
        "hover_on_high_liquidation_zones": "鼠标缓慢悬停在高爆仓区域",
        "click_refresh_button": "点击页面刷新按钮",
        "move_mouse_to_support_level": "鼠标移动至支撑位区域",
    }

    for shot in shots:
        sid         = shot.get("id", "?")
        start       = shot.get("start_sec", 0)
        end         = shot.get("end_sec", 0)
        duration    = shot.get("duration_sec", end - start)
        url         = shot.get("url", "（无 URL）")
        view        = shot.get("view", "")
        scroll      = shot.get("scroll_behavior", "none")
        action      = shot.get("action", "")
        interaction = shot.get("interaction", "")
        text_clip   = shot.get("text_clip", "")
        notes       = shot.get("notes", "")

        scroll_zh = action_desc.get(scroll, scroll)
        action_zh = action_desc.get(action, action)

        lines += [
            f"\n── 分镜 {sid}/{len(shots)} ──────────────────────",
            f"⏱  停留时长：{duration:.1f} 秒（视频时间轴：{start:.1f}s - {end:.1f}s）",
            f"🌐 打开页面：{url}",
        ]
        if view:
            lines.append(f"🔍 聚焦区域：{view}（将该区域置于屏幕中央）")
        if scroll not in ("none", "static_view", ""):
            lines.append(f"📜 页面操作：{scroll_zh}")
        elif action and action not in ("static_view", "none", ""):
            lines.append(f"🖱  页面操作：{action_zh}")
        else:
            lines.append(f"📌 页面操作：固定展示，保持静止 {duration:.1f} 秒")
        if interaction:
            lines.append(f"⌨  额外交互：{interaction}")
        if text_clip:
            clip = text_clip[:100] + ("..." if len(text_clip) > 100 else "")
            lines.append(f"🎤 同步台词：{clip}")
        if notes:
            lines.append(f"📝 备注：{notes}")

    lines += [
        "\n" + "=" * 50,
        f"✅ 以上共 {len(shots)} 个分镜，合计约 {total_duration:.0f} 秒。",
        "✅ 请全程保持录屏，操作完所有分镜后停止录制，保存为一个完整视频文件。",
        "✅ 完成后请回复：完成",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 主工作流（可被 web 层调用）
# --------------------------------------------------------------------------- #

def run_workflow(
    prompt: str,
    log_fn: Optional[Callable] = None,
    outputs_base: str = "outputs",
    wait_for_openclaw: bool = True,
    duration_minutes: int = VIDEO_DURATION_MINUTES,
) -> dict:
    """
    执行完整的 AI 视频内容生成流程。

    参数
    ----
    prompt            创作提示词
    log_fn            进度回调，签名为 log_fn(step, msg, **extra)
                      step 取值：'script' / 'audio' / 'storyboard' / 'openclaw' / 'pipeline' / 'done' / 'error'
                      web 层通过此回调推送 SSE 事件
    outputs_base      输出根目录，默认 "outputs"
    wait_for_openclaw True（默认）= 发送指令后阻塞等待 OpenClaw 回复"完成"；
                      False = 发送后立即跳过等待，直接用 video_shoot/ 中现有录屏继续合成
    duration_minutes  目标视频时长（分钟），会注入到文稿和分镜提示词中，默认取 config.VIDEO_DURATION_MINUTES

    返回
    ----
    dict 包含所有产物路径和内容
    """

    def emit(step: str, msg: str, **extra):
        if log_fn:
            log_fn(step, msg, **extra)
        log(msg)

    # ── 1. 创建输出目录 ───────────────────────────────────────────────────
    folder_name      = "视频_" + datetime.now().strftime("%Y%m%d_%H%M")
    run_dir          = os.path.join(outputs_base, folder_name)
    os.makedirs(run_dir, exist_ok=True)
    script_path          = os.path.join(run_dir, "script.txt")
    audio_path           = os.path.join(run_dir, "audio.mp3")
    storyboard_path      = os.path.join(run_dir, "storyboard.txt")
    storyboard_xlsx_path = os.path.join(run_dir, "storyboard.xlsx")
    recording_task_path  = os.path.join(run_dir, "recording_task.txt")

    emit("script", f"输出目录已创建: {run_dir}", folder=folder_name)

    # ── 2. 生成口播文稿 ───────────────────────────────────────────────────
    emit("script", f"调用 Gemini 生成口播文稿（目标时长 {duration_minutes} 分钟）...")
    duration_note = f"\n\n[时长要求：文稿朗读时长约 {duration_minutes} 分钟，请严格控制内容长度。]"
    try:
        script = gemini_complete(prompt + duration_note)
    except Exception as e:
        emit("error", f"文稿生成失败: {e}")
        raise

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    emit("script", f"文稿已保存 ({len(script)} 字符)", artifact="script", path=script_path)

    # ── 3. 文字转语音 ─────────────────────────────────────────────────────
    emit("audio", "调用 ElevenLabs 生成音频...")
    try:
        text_to_speech_to_file(script, audio_path)
    except Exception as e:
        emit("error", f"音频生成失败: {e}")
        raise

    emit("audio", "音频已保存", artifact="audio", path=audio_path)

    # ── 4. 生成分镜 JSON ──────────────────────────────────────────────────
    emit("storyboard", "调用 Gemini 生成分镜...")
    try:
        storyboard_text = gemini_complete(build_storyboard_prompt(script, duration_minutes))
    except Exception as e:
        emit("error", f"分镜生成失败: {e}")
        raise

    with open(storyboard_path, "w", encoding="utf-8") as f:
        f.write(storyboard_text)

    # 解析 JSON（清理可能的 markdown 围栏）
    shots = []
    storyboard_xlsx_path_final = None
    clean_text = storyboard_text.strip()
    if clean_text.startswith("```"):
        clean_text = clean_text.split("\n", 1)[-1].rsplit("```", 1)[0]

    try:
        _data = json.loads(clean_text)
        shots = _data["shots"] if isinstance(_data, dict) and "shots" in _data else _data
        emit("storyboard", f"分镜解析成功，共 {len(shots)} 个镜头", shots=shots)
    except Exception as e:
        emit("storyboard", f"分镜 JSON 解析失败（将跳过录屏步骤）: {e}")

    # 导出 Excel
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "storyboard"
        headers = ["id", "start_sec", "end_sec", "duration_sec", "page_type",
                   "source", "url", "view", "scroll_behavior", "action",
                   "interaction", "text_clip", "notes"]
        ws.append(headers)
        for item in shots:
            ws.append([
                item.get("id"), item.get("start_sec"), item.get("end_sec"),
                item.get("duration_sec"), item.get("page_type"), item.get("source"),
                item.get("url"), item.get("view"), item.get("scroll_behavior"),
                item.get("action"), item.get("interaction"),
                item.get("text") or item.get("text_clip"), item.get("notes"),
            ])
        wb.save(storyboard_xlsx_path)
        storyboard_xlsx_path_final = storyboard_xlsx_path
        emit("storyboard", "分镜 Excel 已生成", artifact="storyboard_xlsx", path=storyboard_xlsx_path)
    except Exception as e:
        emit("storyboard", f"Excel 生成失败: {e}")

    # ── 5. 构建录屏指令 + 发送给 OpenClaw ────────────────────────────────
    openclaw_reply    = None
    pipeline_ready    = False   # 是否可以进入视频合成步骤

    if shots:
        recording_instruction = build_recording_instruction(shots, folder_name)
        with open(recording_task_path, "w", encoding="utf-8") as f:
            f.write(recording_instruction)
        emit("openclaw", "录屏指令已生成，正在通过飞书发送给 OpenClaw...",
             artifact="recording_task", path=recording_task_path)

        if wait_for_openclaw:
            # ── 模式 A：等待回复 ──────────────────────────────────────────
            emit("openclaw", "等待 OpenClaw 回复（最多 600 秒）...")
            try:
                openclaw_reply = send_as_user_and_wait_reply(recording_instruction, timeout=600)
                if openclaw_reply:
                    emit("openclaw", f"OpenClaw 回复: {openclaw_reply}", reply=openclaw_reply)
                    pipeline_ready = True
                else:
                    emit("openclaw", "未收到 OpenClaw 回复（超时）。如已录制完成，请手动将视频放入 video_shoot/ 后重新触发合成。")
            except Exception as e:
                emit("openclaw", f"发送飞书消息失败: {e}")
        else:
            # ── 模式 B：不等待，直接用现有录屏 ──────────────────────────
            try:
                from openclaw import send_as_user_and_wait_reply as _send_only
                # 只发送，不阻塞等待（timeout=0 表示不监听回复）
                send_as_user_and_wait_reply(recording_instruction, timeout=0)
            except Exception as e:
                emit("openclaw", f"发送飞书消息失败（已忽略）: {e}")
            emit("openclaw", "已发送录屏指令，跳过等待回复 → 直接使用 video_shoot/ 中现有录屏。",
                 reply="跳过等待")
            pipeline_ready = True
    else:
        recording_task_path = None
        emit("openclaw", "分镜解析失败，跳过录屏指令发送。")

    # ── 6. 视频合成流水线（pipeline.build_video）────────────────────────
    final_video_path = None
    if pipeline_ready and shots:
        final_video_path = _run_pipeline(
            audio_path=audio_path,
            shots=shots,
            folder_name=folder_name,
            run_dir=run_dir,
            emit=emit,
        )
    else:
        if shots:
            emit("pipeline", "跳过视频合成（等待 OpenClaw 超时或分镜为空）。")
        # shots 为空时已在上方打印，无需重复

    # ── 7. 完成汇总 ───────────────────────────────────────────────────────
    artifacts = {
        "folder":            folder_name,
        "run_dir":           run_dir,
        "script":            script_path,
        "audio":             audio_path,
        "storyboard_txt":    storyboard_path,
        "storyboard_xlsx":   storyboard_xlsx_path_final,
        "recording_task":    recording_task_path,
        "shots":             shots,
        "openclaw_reply":    openclaw_reply,
        "final_video":       final_video_path,
    }
    emit("done", "全部流程已完成。", artifacts=artifacts)
    return artifacts


# --------------------------------------------------------------------------- #
# 视频合成子流程
# --------------------------------------------------------------------------- #

DEFAULT_RECORDING = "crypto-demo-fullscreen.mp4"   # 默认录屏文件名


def _find_latest_recording(filename: str = DEFAULT_RECORDING) -> Optional[str]:
    """
    在 video_shoot/ 目录中查找录屏文件。
    优先返回 filename 指定的文件；若不存在则返回最新修改时间的 .mp4。
    """
    if not os.path.isdir(_VIDEO_SHOOT_DIR):
        return None

    # 优先查找指定文件名
    target = os.path.join(_VIDEO_SHOOT_DIR, filename)
    if os.path.exists(target):
        return target

    # fallback：取最新修改的 .mp4
    mp4s = [
        os.path.join(_VIDEO_SHOOT_DIR, f)
        for f in os.listdir(_VIDEO_SHOOT_DIR)
        if f.lower().endswith(".mp4")
    ]
    if not mp4s:
        return None
    latest = max(mp4s, key=os.path.getmtime)
    log(f"[pipeline] 未找到 {filename}，使用最新文件: {os.path.basename(latest)}")
    return latest


def _build_clip_list(shots: list) -> List[str]:
    """
    根据分镜列表决定使用哪些 action_clips。
    有 look/side/screen 动作的镜头用 look_side_screen 片段，其余用 idle。
    """
    idle = os.path.join(_ACTION_CLIPS_DIR, "idle_hands_open.mp4")
    look = os.path.join(_ACTION_CLIPS_DIR, "look_side_screen.mp4")

    clips = []
    for shot in shots:
        action = (shot.get("action", "") + shot.get("scroll_behavior", "")).lower()
        target = look if ("look" in action or "side" in action or "screen" in action) else idle
        clips.append(target if os.path.exists(target) else idle)

    # 至少保留 3 个片段
    while len(clips) < 3 and os.path.exists(idle):
        clips.append(idle)

    return [c for c in clips if os.path.exists(c)]


def _run_pipeline(
    audio_path: str,
    shots: list,
    folder_name: str,
    run_dir: str,
    emit,
) -> Optional[str]:
    """调用 pipeline.build_video() 完成视频合成。"""
    # 找录屏文件：优先 DEFAULT_RECORDING，找不到则取最新 .mp4
    main_path = _find_latest_recording()
    if not main_path:
        emit("pipeline", "未在 video_shoot/ 找到录屏文件，跳过视频合成。")
        return None
    emit("pipeline", f"录屏文件: {os.path.basename(main_path)}"
         + ("（默认）" if os.path.basename(main_path) == DEFAULT_RECORDING else "（最新文件）"))

    # 猪头视频
    pig_path = os.path.join(_ACTION_CLIPS_DIR, "pig.mp4")
    if not os.path.exists(pig_path):
        emit("pipeline", f"未找到猪头视频 {pig_path}，跳过视频合成。")
        return None

    # 动作片段列表
    clip_paths = _build_clip_list(shots)
    if not clip_paths:
        emit("pipeline", "未找到任何 action_clips，跳过视频合成。")
        return None

    emit("pipeline", f"动作片段 {len(clip_paths)} 个 | 猪头: {os.path.basename(pig_path)}")

    # 目标时长（取分镜最大 end_sec）
    target_duration = max((s.get("end_sec", 0) for s in shots), default=60.0)

    output_path = os.path.join(run_dir, "final.mp4")
    work_dir    = os.path.join(run_dir, "video_work")

    emit("pipeline", f"开始合成，目标时长: {target_duration:.0f}s → {os.path.basename(output_path)}")

    try:
        from pipeline import build_video
        result = build_video(
            clip_paths=clip_paths,
            audio_path=audio_path,
            pig_path=pig_path,
            main_path=main_path,
            output_path=output_path,
            target_duration=target_duration,
            work_dir=work_dir,
            skip_existing=False,
        )
        emit("pipeline", f"视频合成完成: {os.path.basename(result)}",
             artifact="final_video", path=result)
        return result
    except Exception as e:
        emit("pipeline", f"视频合成失败: {e}")
        return None


# --------------------------------------------------------------------------- #
# CLI 入口
# --------------------------------------------------------------------------- #

def main():
    log("启动视频内容生成流程。")
    prompt = input("请输入创作提示词（直接回车用默认）: ").strip() or DEFAULT_PROMPT

    dur_input = input(f"目标视频时长（分钟，直接回车默认 {VIDEO_DURATION_MINUTES} 分钟）: ").strip()
    duration = int(dur_input) if dur_input.isdigit() else VIDEO_DURATION_MINUTES

    ans = input("发送录屏指令后是否等待 OpenClaw 回复？(y=等待[默认] / n=发送后直接用现有录屏继续): ").strip().lower()
    wait = (ans != "n")

    artifacts = run_workflow(prompt, wait_for_openclaw=wait, duration_minutes=duration)

    print("\n" + "=" * 50)
    print("生成结果汇总：")
    print(f"  文稿        : {artifacts['script']}")
    print(f"  音频        : {artifacts['audio']}")
    print(f"  故事板(txt) : {artifacts['storyboard_txt']}")
    print(f"  故事板(xlsx): {artifacts['storyboard_xlsx'] or '生成失败'}")
    print(f"  录屏指令    : {artifacts['recording_task'] or '（分镜解析失败，未生成）'}")
    print(f"  最终视频    : {artifacts['final_video'] or '（未生成）'}")
    print("=" * 50)


if __name__ == "__main__":
    main()
