"""
完整流程：
  1. 拼接 action_clips 视频（idle 多次使用），总时长裁到 60s
  2. 替换音频为 test/audio.mp3
  3. 全尺寸替换人物头部为猪头（1920x1080，人脸检测精度最高）
  4. 以猪头视频为画中画，叠加到 test/crypto-demo-fullscreen.mp4 右下角
"""
import os
import logging

from moviepy import VideoFileClip, concatenate_videoclips
from synthesis import overlay, replace_audio, replace_head

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── 路径配置 ──────────────────────────────────────
IDLE  = "action_clips/idle_hands_open.mp4"
LOOK  = "action_clips/look_side_screen.mp4"
AUDIO = "test/audio.mp3"
MAIN  = "test/crypto-demo-fullscreen.mp4"

PIG   = "action_clips/pig.mp4"

OUT_DIR       = "output"
OUT_CONCAT    = f"{OUT_DIR}/step1_concat.mp4"
OUT_REPLACED  = f"{OUT_DIR}/step2_audio_replaced.mp4"
OUT_PIG_HEAD  = f"{OUT_DIR}/step3_pig_head.mp4"
OUT_FINAL     = f"{OUT_DIR}/final.mp4"

TARGET_DURATION = 60.0  # 目标总时长（秒）

os.makedirs(OUT_DIR, exist_ok=True)


# ── Step 1：拼接并裁剪到 60s ──────────────────────
# idle(22.82) + look(21.36) + idle(22.82) = 67s → subclip 到 60s
# idle 使用了 2 次，满足"多次使用"要求
log.info("=== Step 1：拼接视频，目标时长 %.0fs ===", TARGET_DURATION)

clip_paths = [IDLE, LOOK, IDLE]
clips = [VideoFileClip(p) for p in clip_paths]
log.info("拼接顺序：%s", " → ".join(os.path.basename(p) for p in clip_paths))

merged = concatenate_videoclips(clips, method="compose")
log.info("拼接后总时长：%.2fs，裁剪至 %.0fs", merged.duration, TARGET_DURATION)

trimmed = merged.subclipped(0, TARGET_DURATION)
trimmed.write_videofile(OUT_CONCAT, codec="libx264", audio_codec="aac", logger="bar")

merged.close()
trimmed.close()
for c in clips:
    c.close()
log.info("Step 1 完成：%s", OUT_CONCAT)


# ── Step 2：替换音频 ──────────────────────────────
log.info("=== Step 2：替换音频 ===")
replace_audio(
    video_path=OUT_CONCAT,
    audio_path=AUDIO,
    output_path=OUT_REPLACED,
    loop_audio=True,   # 音频不足 60s 时自动循环
)
log.info("Step 2 完成：%s", OUT_REPLACED)


# ── Step 3：猪头替换（全尺寸 1920x1080，检测最准）────
# 在缩小之前替换头部，人脸有 200~300px 大，检测精度远高于 PiP 小窗内操作
log.info("=== Step 3：猪头替换 ===")
replace_head(
    video_path=OUT_REPLACED,
    pig_path=PIG,
    output_path=OUT_PIG_HEAD,
    head_scale=4,        # 猪头是人脸 bbox 的 1.8 倍，盖住头发和额头
    y_offset_ratio=0.25,   # 猪头中心向上偏移 25%（猪头头顶比人脸占比更大）
    smooth_window=5,       # 5 帧滑动平均，消除检测抖动
    white_thresh=240,      # 白色背景抠图阈值
    keep_audio=True,
)
log.info("Step 3 完成：%s", OUT_PIG_HEAD)


# ── Step 4：画中画叠加到主视频右下角 ─────────────
log.info("=== Step 4：画中画合成 ===")
overlay(
    main_path=MAIN,
    sub_path=OUT_PIG_HEAD,           # 使用猪头版本作为 PiP 小窗
    output_path=OUT_FINAL,
    position="bottom-right",
    sub_scale=0.18,
    margin=20,
    main_audio=False,
    sub_audio=True,
    sub_crop=(656, 0, 1263, 1080),   # 裁掉左右白边，保留人物区域
)
log.info("Step 4 完成：%s", OUT_FINAL)

log.info("=== 全部完成，最终文件：%s ===", OUT_FINAL)
