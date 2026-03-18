#!/usr/bin/env python3
"""
测试：固定位置叠加模式（无 face detection，纯 FFmpeg，大幅加速 Step 3）

运行：cd /root/project/ai_video && python3 test_fixed_overlay.py

输出保存到 test/ 文件夹。
"""
import os
import sys
import logging
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "video_module"))

# 输出目录
TEST_DIR = ROOT / "test"
TEST_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    # 路径配置（使用项目现有素材）
    action_clips = ROOT / "video_module" / "action_clips"
    video_shoot = ROOT / "video_module" / "video_shoot"
    outputs = ROOT / "outputs"

    # 数字人片段（jirian 文件夹）
    digital_folder = action_clips / "jirian"
    clip_paths = sorted(digital_folder.glob("*.mp4"))
    if not clip_paths:
        log.error("未找到数字人片段，请检查 %s", digital_folder)
        return 1
    clip_paths = [str(p) for p in clip_paths[:3]]  # 最多用 3 个

    # 卡通头部
    pig_path = str(action_clips / "pig.mp4")
    if not os.path.exists(pig_path):
        log.error("未找到卡通头视频: %s", pig_path)
        return 1

    # 音频：从已有 output 取，或需要 TTS
    audio_candidates = list(outputs.rglob("audio.mp3"))
    if not audio_candidates:
        log.error("未找到 audio.mp3，请先在 outputs/ 下运行一次录屏流程生成音频")
        return 1
    audio_path = str(max(audio_candidates, key=os.path.getmtime))

    # 主视频（录屏）
    main_candidates = list(video_shoot.glob("*.mp4"))
    if not main_candidates:
        log.error("未找到录屏视频: %s", video_shoot)
        return 1
    main_path = str(max(main_candidates, key=os.path.getmtime))

    # 清理旧中间文件，避免脏数据
    work_dir = str(TEST_DIR / "work")
    import shutil
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    # 目标时长：15 秒快速测试（全 FFmpeg 路径，数十秒内完成）
    target_duration = 15.0
    from moviepy import AudioFileClip
    with AudioFileClip(audio_path) as ac:
        audio_dur = ac.duration
    if audio_dur < target_duration:
        target_duration = round(audio_dur, 2)
    # 截断音频到 target_duration，确保 Step 2 可走 FFmpeg 快速路径
    audio_trimmed = str(TEST_DIR / "work" / "_audio_trimmed.mp3")
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-i", audio_path, "-t", str(target_duration), "-acodec", "copy", audio_trimmed],
                   check=True, capture_output=True)
    audio_path = audio_trimmed
    log.info("测试时长 %.1fs", target_duration)

    path_concat = os.path.join(work_dir, "_step1_concat.mp4")
    path_audio = os.path.join(work_dir, "_step2_audio.mp4")
    path_pig_fixed = os.path.join(work_dir, "_step3_pig_fixed.mp4")  # 固定叠加，无检测
    output_path = str(TEST_DIR / "final_fixed_overlay.mp4")

    from core.ffmpeg_fast import (
        concat_and_trim,
        replace_audio_fast,
        overlay_cartoon_fixed,
        overlay_fast,
        _ffmpeg_available,
    )

    if not _ffmpeg_available():
        log.error("ffmpeg 未安装")
        return 1

    # Step 1：拼接数字人
    log.info("=== Step 1：拼接 %d 个数字人片段，裁剪至 %.1fs ===", len(clip_paths), target_duration)
    concat_and_trim(clip_paths, path_concat, target_duration, "ultrafast")

    # Step 2：替换音频（FFmpeg -c:v copy 快速路径，无 MoviePy 回退）
    log.info("=== Step 2：替换音频（TTS）===")
    replace_audio_fast(path_concat, audio_path, path_audio, trim_to_audio=True, ffmpeg_preset="ultrafast")

    # Step 3：固定位置叠加卡通头（无 face detection，纯 FFmpeg）
    log.info("=== Step 3：固定位置叠加卡通头（快速模式，无检测）===")
    overlay_cartoon_fixed(
        path_audio, pig_path, path_pig_fixed,
        cartoon_scale=0.35,   # 卡通头宽度占数字人画面 35%
        cartoon_y_ratio=0.12, # 垂直位于画面上部 12% 处（中上）
        ffmpeg_preset="ultrafast",
    )

    # Step 4：画中画叠到录屏右下角
    log.info("=== Step 4：画中画叠到录屏右下角 ===")
    overlay_fast(
        main_path=main_path,
        sub_path=path_pig_fixed,
        output_path=output_path,
        position="bottom-right",
        sub_scale=0.18,
        margin=20,
        sub_crop=(656, 0, 1263, 1080),
        main_audio=False,
        sub_audio=True,
        target_duration=target_duration,
        ffmpeg_preset="ultrafast",
    )

    log.info("=== 完成！输出：%s ===", output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
