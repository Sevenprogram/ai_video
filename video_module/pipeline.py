"""
视频合成完整流水线，封装为单个可调用函数。

流程：
  Step 1  拼接多个 action_clips 视频，裁剪到目标时长
  Step 2  替换音频（视频时长以音频为准：不足则循环、超出则裁剪）
  Step 3  全尺寸替换人物头部为卡通头像（检测精度最高）
  Step 4  以猪头视频为画中画叠加到主视频右下角

时长规则（audio_as_canonical=True 时）：
  - 最终时长 = 音频时长
  - 音频 > 录屏：录屏最后一帧冻结延长
  - 音频 < 录屏：录屏与数字人均裁剪至音频长度

调用示例：
    from pipeline import build_video

    build_video(
        clip_paths=["action_clips/idle_hands_open.mp4",
                    "action_clips/look_side_screen.mp4",
                    "action_clips/idle_hands_open.mp4"],
        audio_path="test/audio.mp3",
        pig_path="action_clips/pig.mp4",
        main_path="test/crypto-demo-fullscreen.mp4",
        output_path="output/final.mp4",
    )
"""
import logging
import os
import tempfile
from typing import List, Optional, Tuple

from moviepy import AudioFileClip, VideoFileClip, concatenate_videoclips
from synthesis import overlay, replace_audio, replace_head

log = logging.getLogger(__name__)


def build_video(
    clip_paths: List[str],
    audio_path: str,
    pig_path: str,
    main_path: str,
    output_path: str,
    # 时长控制
    target_duration: float = 60.0,
    audio_as_canonical: bool = False,
    # 猪头参数
    head_scale: float = 1.8,
    y_offset_ratio: float = 0.25,
    smooth_window: int = 5,
    white_thresh: int = 240,
    # PiP 参数
    pip_scale: float = 0.18,
    pip_position: str = "bottom-right",
    pip_margin: int = 20,
    pip_crop: Optional[Tuple[int, int, int, int]] = (656, 0, 1263, 1080),
    # 中间文件目录
    work_dir: str = "output",
    # 是否跳过已存在的中间步骤（断点续跑）
    skip_existing: bool = False,
    # 编码加速（preset: ultrafast/fast/medium）
    ffmpeg_preset: str = "fast",
) -> str:
    """
    完整视频合成流水线。

    参数：
        clip_paths         : action_clips 视频列表，按顺序拼接（可重复使用同一文件）
        audio_path         : 替换用音频路径
        pig_path           : 卡通头部视频路径（白色背景 MP4）
        main_path          : 主视频路径（画中画的背景大画面）
        output_path        : 最终输出 MP4 路径
        target_duration    : 拼接后裁剪的目标时长（秒），默认 60；audio_as_canonical 时会被覆盖
        audio_as_canonical : True 时以音频时长为准，录屏/数字人自动裁剪或延长
        head_scale         : 猪头相对人脸 bbox 的缩放倍数，默认 1.8
        ffmpeg_preset      : 编码预设 ultrafast/fast/medium，加速用 ultrafast
        y_offset_ratio  : 猪头中心向上偏移比例，默认 0.25
        smooth_window   : 人脸 bbox 平滑窗口帧数，默认 5
        white_thresh    : 白色背景抠图阈值，默认 240
        pip_scale       : PiP 小窗宽度占主视频比例，默认 0.18
        pip_position    : PiP 位置，默认 'bottom-right'
        pip_margin      : PiP 距边缘像素，默认 20
        pip_crop        : PiP 小窗裁剪区域 (x1,y1,x2,y2)，去除白边
        work_dir        : 中间文件存放目录，默认 'output'
        skip_existing   : True 时跳过已存在的中间步骤，方便断点续跑

    返回：
        output_path
    """
    os.makedirs(work_dir, exist_ok=True)

    # 以音频为时长基准时，优先使用音频时长
    if audio_as_canonical:
        with AudioFileClip(audio_path) as ac:
            target_duration = round(ac.duration, 2)
        log.info("以音频为时长基准：%.2fs", target_duration)

    ffmpeg_params = ["-preset", ffmpeg_preset]

    # 中间文件路径
    path_concat   = os.path.join(work_dir, "_step1_concat.mp4")
    path_audio    = os.path.join(work_dir, "_step2_audio.mp4")
    path_pig_head = os.path.join(work_dir, "_step3_pig_head.mp4")

    # ── Step 1：拼接 & 裁剪 ────────────────────────────
    if skip_existing and os.path.exists(path_concat):
        log.info("Step 1 跳过（已存在）：%s", path_concat)
    else:
        log.info("=== Step 1：拼接 %d 个视频，裁剪至 %.0fs ===",
                 len(clip_paths), target_duration)
        clips = [VideoFileClip(p) for p in clip_paths]
        merged = concatenate_videoclips(clips, method="compose")
        trimmed = merged.subclipped(0, min(target_duration, merged.duration))
        trimmed.write_videofile(path_concat, codec="libx264",
                                audio_codec="aac", logger="bar",
                                ffmpeg_params=ffmpeg_params)
        trimmed.close()
        merged.close()
        for c in clips:
            c.close()
        log.info("Step 1 完成：%s（%.2fs）", path_concat, target_duration)

    # ── Step 2：替换音频 ───────────────────────────────
    if skip_existing and os.path.exists(path_audio):
        log.info("Step 2 跳过（已存在）：%s", path_audio)
    else:
        log.info("=== Step 2：替换音频 ===")
        replace_audio(
            video_path=path_concat,
            audio_path=audio_path,
            output_path=path_audio,
            loop_audio=not audio_as_canonical,
            trim_to_audio=audio_as_canonical,
            ffmpeg_params=ffmpeg_params,
        )
        log.info("Step 2 完成：%s", path_audio)

    # ── Step 3：猪头替换（全尺寸，检测精度最高）─────────
    if skip_existing and os.path.exists(path_pig_head):
        log.info("Step 3 跳过（已存在）：%s", path_pig_head)
    else:
        log.info("=== Step 3：猪头替换 ===")
        replace_head(
            video_path=path_audio,
            pig_path=pig_path,
            output_path=path_pig_head,
            head_scale=head_scale,
            y_offset_ratio=y_offset_ratio,
            smooth_window=smooth_window,
            white_thresh=white_thresh,
            keep_audio=True,
            ffmpeg_params=ffmpeg_params,
        )
        log.info("Step 3 完成：%s", path_pig_head)

    # ── Step 4：画中画合成 ─────────────────────────────
    log.info("=== Step 4：画中画合成 ===")
    overlay(
        main_path=main_path,
        sub_path=path_pig_head,
        output_path=output_path,
        position=pip_position,
        sub_scale=pip_scale,
        margin=pip_margin,
        main_audio=False,
        sub_audio=True,
        sub_crop=pip_crop,
        target_duration=target_duration if audio_as_canonical else None,
        ffmpeg_params=ffmpeg_params,
    )
    log.info("=== 全部完成，输出：%s ===", output_path)
    return output_path


# ── 直接运行时的默认配置 ──────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    build_video(
        clip_paths=[
            "action_clips/idle_hands_open.mp4",
            "action_clips/look_side_screen.mp4",
            "action_clips/idle_hands_open.mp4",
        ],
        audio_path="test/audio.mp3",
        pig_path="action_clips/pig.mp4",
        main_path="test/crypto-demo-fullscreen.mp4",
        output_path="output/final.mp4",
        target_duration=60.0,
        skip_existing=True,   # 已完成的步骤直接跳过，节省时间
    )
