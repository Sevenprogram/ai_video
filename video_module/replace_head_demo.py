"""
头部替换测试脚本
用 action_clips/pig.mp4 替换 action_clips/idle_hands_open.mp4 中的人脸
"""
import logging
from synthesis import replace_head

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

replace_head(
    video_path="action_clips/idle_hands_open.mp4",
    pig_path="action_clips/pig.mp4",
    output_path="output/pig_head_result.mp4",
    head_scale=1.8,       # 猪头是人脸的 1.8 倍大（盖住头发额头）
    y_offset_ratio=0.25,  # 猪头中心向上偏移 25%（猪头头顶比人脸多）
    smooth_window=5,      # 5 帧滑动平均，消除检测抖动
    white_thresh=240,     # 白色背景阈值
)
