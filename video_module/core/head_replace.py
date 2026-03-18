"""
头部替换模块（简化版）：直接用 FFmpeg 覆盖卡通头部

方法：使用 FFmpeg 的 colorkey 滤镜去除白色背景，然后 overlay 到数字人视频上。
不需要人脸检测，速度极快。

注意：适用于数字人视频（固定机位），卡通头部和数字人视频需要事先对齐位置。
"""
import logging
import os
import subprocess
import sys
from typing import Optional, List

import cv2

# 导入配置
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import CARTOON_HEAD_WHITE_THRESH

from .utils import check_video_path, ensure_output_dir

logger = logging.getLogger(__name__)


def _get_video_info(path: str) -> dict:
    """获取视频基本信息"""
    cap = cv2.VideoCapture(path)
    info = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    cap.release()
    return info


def replace_head(
    video_path: str,
    pig_path: str,
    output_path: str,
    head_scale: float = 1.0,
    y_offset_ratio: float = 0.0,
    smooth_window: int = 5,
    white_thresh: int = CARTOON_HEAD_WHITE_THRESH,
    keep_audio: bool = True,
    ffmpeg_params: Optional[List[str]] = None,
    detect_interval: int = 30,
    detect_once: bool = True,
    # 新参数：指定卡通头部覆盖位置（相对于视频宽度，0.0-1.0）
    overlay_x: float = 0.5,  # 水平位置，0.5 表示居中
    overlay_y: float = 0.38,  # 垂直位置，0.38 表示略偏下
    overlay_scale: float = 0.48,  # 卡通头部相对视频宽度的缩放比例
) -> str:
    """
    用卡通头部视频直接覆盖到原视频上（FFmpeg 方式，极速）。

    参数：
        video_path      : 原始数字人视频路径
        pig_path        : 卡通头部视频路径（白色背景 MP4）
        output_path     : 输出 MP4 路径
        overlay_x       : 卡通头部水平位置（0.0-1.0），默认 0.5（居中）
        overlay_y       : 卡通头部垂直位置（0.0-1.0），默认 0.3（顶部 30%）
        overlay_scale   : 卡通头部相对视频宽度的缩放比例，默认 0.4
        white_thresh    : 白色背景阈值（0-255），默认 240
        keep_audio      : 是否保留原视频音频，默认 True

    返回：
        output_path
    """
    check_video_path(video_path)
    check_video_path(pig_path)
    ensure_output_dir(output_path)

    logger.info("=== 头部替换（FFmpeg 直接覆盖模式）===")
    logger.info("原始视频：%s", video_path)
    logger.info("卡通头部：%s", pig_path)
    logger.info("输出路径：%s", output_path)

    # 获取视频信息
    video_info = _get_video_info(video_path)
    pig_info = _get_video_info(pig_path)
    vw, vh = video_info["width"], video_info["height"]
    pw, ph = pig_info["width"], pig_info["height"]

    logger.info("原始视频：%dx%d", vw, vh)
    logger.info("卡通头部：%dx%d", pw, ph)

    # 计算卡通头部的目标尺寸
    target_width = int(vw * overlay_scale)
    target_height = int(target_width * ph / pw)  # 保持宽高比

    # 计算覆盖位置（像素坐标）
    x = int(vw * overlay_x - target_width / 2)
    y = int(vh * overlay_y - target_height / 2)

    logger.info("卡通头部目标尺寸：%dx%d", target_width, target_height)
    logger.info("覆盖位置：(%d, %d)", x, y)

    # 计算白色阈值（colorkey 使用 RGB，需要转换）
    # white_thresh 是灰度阈值（0-255），转换为 RGB 近似值
    # colorkey 的 similarity 参数范围：0.01-1.0（浮点数）
    # white_thresh=240 意味着 RGB 值都 >=240 的被认为是白色
    # 转换公式：(255 - white_thresh) / 255 得到 0-1 范围的相似度
    similarity = max(0.01, min(1.0, (255 - white_thresh) / 255.0))
    logger.info("白色背景阈值：%d（similarity=%.2f）", white_thresh, similarity)

    # 临时文件
    tmp_pig = output_path.replace(".mp4", "_pig_processed.mp4")

    # 构建 FFmpeg 命令
    # 方案：
    # 1. 使用 colorkey 滤镜去除白色背景（白色变透明）
    # 2. 缩放卡通头部
    # 3. 叠加到主视频上
    
    # 第一次处理：去除白色背景并缩放
    cmd_preprocess = [
        "ffmpeg", "-y",
        "-i", pig_path,
        "-vf", f"colorkey=0xFFFFFF:{similarity}:0.0,scale={target_width}:{target_height}",
        "-c:v", "libvpx",  # VP9 支持透明度
        "-crf", "30",
        "-b:v", "0",
        tmp_pig
    ]
    
    logger.info("预处理卡通头部（去白底 + 缩放）...")
    try:
        result = subprocess.run(
            cmd_preprocess,
            check=True,
            capture_output=True,
            text=True
        )
        logger.info("预处理完成")
    except subprocess.CalledProcessError as e:
        logger.warning("VP9 编码失败，回退到 PNG 序列方式: %s", e.stderr)
        # 回退方案：使用 overlay 滤镜链直接处理
        cmd = _build_ffmpeg_command(
            video_path, pig_path, output_path,
            x, y, target_width, target_height,
            white_thresh, similarity, keep_audio
        )
        logger.info("使用滤镜链方式执行...")
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info("头部替换完成（滤镜链模式），输出：%s", output_path)
        return output_path

    # 第二次处理：叠加到主视频（-r 25 恒定帧率减轻卡顿）
    if keep_audio:
        cmd_overlay = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", tmp_pig,
            "-filter_complex",
            f"[1:v]format=rgba[fg];[0:v][fg]overlay={x}:{y}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-r", "25",
            "-c:a", "copy",
            output_path
        ]
    else:
        cmd_overlay = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", tmp_pig,
            "-filter_complex",
            f"[1:v]format=rgba[fg];[0:v][fg]overlay={x}:{y}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-r", "25",
            output_path
        ]

    logger.info("叠加卡通头部到视频...")
    try:
        result = subprocess.run(
            cmd_overlay,
            check=True,
            capture_output=True,
            text=True
        )
        logger.info("叠加完成")
    except subprocess.CalledProcessError as e:
        logger.error("叠加失败，回退到滤镜链方式: %s", e.stderr)
        cmd = _build_ffmpeg_command(
            video_path, pig_path, output_path,
            x, y, target_width, target_height,
            white_thresh, similarity, keep_audio
        )
        subprocess.run(cmd, check=True, capture_output=True)

    # 清理临时文件
    if os.path.exists(tmp_pig):
        os.remove(tmp_pig)

    logger.info("头部替换完成，输出：%s", output_path)
    return output_path


def _build_ffmpeg_command(
    video_path: str,
    pig_path: str,
    output_path: str,
    x: int, y: int,
    target_width: int, target_height: int,
    white_thresh: int,
    similarity: float,
    keep_audio: bool,
) -> List[str]:
    """构建使用滤镜链的 FFmpeg 命令（回退方案）。输出视频带 [outv] 标签，保证音轨来自第一路输入（ElevenLabs 音频）。"""
    # overlay 输出命名为 [outv]，便于 -map 明确指定音视频流
    filter_complex = (
        f"[1:v]colorkey=0xFFFFFF:{similarity}:0.0,scale={target_width}:{target_height}[pig];"
        f"[0:v][pig]overlay={x}:{y}[outv]"
    )
    if keep_audio:
        return [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", pig_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "0:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-r", "25",
            "-c:a", "copy",
            output_path
        ]
    else:
        return [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", pig_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-r", "25",
            output_path
        ]
