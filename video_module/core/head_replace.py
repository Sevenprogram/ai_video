"""
头部替换模块：用卡通头部视频逐帧覆盖原视频中的人脸区域

流程：
  1. mediapipe 检测每帧人脸 bbox
  2. 对 bbox 做滑动平均，消除检测抖动
  3. 从卡通视频取对应帧（自动循环）
  4. 抠掉卡通帧的纯白背景，生成 alpha 遮罩
  5. 将卡通头按 bbox 缩放后 alpha 混合到原始帧
  6. 所有帧写入临时视频，最后附回原始音频
"""
import logging
import os
import subprocess
import sys
from collections import deque
from typing import Optional, Tuple, List

import cv2
import numpy as np

# 导入配置
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import CARTOON_HEAD_SCALE, CARTOON_HEAD_WHITE_THRESH

from .utils import check_video_path, ensure_output_dir

logger = logging.getLogger(__name__)


# ── 白色背景去除 ───────────────────────────────────

def _remove_white_bg(
    img_bgr: np.ndarray,
    white_thresh: int = CARTOON_HEAD_WHITE_THRESH,
    blur_size: int = 5,
) -> np.ndarray:
    """
    将纯白背景转为透明，返回 BGRA 图像。

    white_thresh : 灰度值超过此阈值视为白色背景（0~255，默认从 config.py 读取）
    blur_size    : 遮罩边缘高斯模糊核大小，0 表示不模糊

    优化：使用向量化操作代替循环，提高处理速度
    """
    # 使用 cv2.inRange 进行向量化阈值处理，比循环快很多
    lower_white = np.array([white_thresh, white_thresh, white_thresh], dtype=np.uint8)
    upper_white = np.array([255, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(img_bgr, lower_white, upper_white)

    # 反转：白色区域变0，非白色变255
    mask = cv2.bitwise_not(mask)

    # 形态学处理：先腐蚀去白边毛刺，再膨胀还原内容
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.erode(mask, kernel, iterations=1)
    mask = cv2.dilate(mask, kernel, iterations=2)

    # 边缘软化，让融合更自然
    if blur_size > 1:
        blur_size = blur_size if blur_size % 2 == 1 else blur_size + 1
        mask = cv2.GaussianBlur(mask, (blur_size, blur_size), 0)

    bgra = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = mask
    return bgra


# ── Alpha 混合 ─────────────────────────────────────

def _alpha_blend(
    background: np.ndarray,
    foreground_bgra: np.ndarray,
    x: int,
    y: int,
) -> np.ndarray:
    """
    将带 alpha 通道的前景图混合到背景的 (x, y) 位置。
    超出背景边界的部分自动裁剪，不会报错。
    """
    bg_h, bg_w = background.shape[:2]
    fg_h, fg_w = foreground_bgra.shape[:2]

    # 计算实际覆盖区域（处理越界情况）
    bx1, by1 = max(0, x), max(0, y)
    bx2, by2 = min(bg_w, x + fg_w), min(bg_h, y + fg_h)

    if bx2 <= bx1 or by2 <= by1:
        return background  # 完全越界，直接返回原图

    # 前景中对应的裁剪区域
    fx1, fy1 = bx1 - x, by1 - y
    fx2, fy2 = fx1 + (bx2 - bx1), fy1 + (by2 - by1)

    fg_roi = foreground_bgra[fy1:fy2, fx1:fx2].astype(np.float32)
    bg_roi = background[by1:by2, bx1:bx2].astype(np.float32)

    # alpha 混合：out = fg * alpha + bg * (1 - alpha)
    alpha = fg_roi[:, :, 3:4] / 255.0
    blended = fg_roi[:, :, :3] * alpha + bg_roi * (1.0 - alpha)

    result = background.copy()
    result[by1:by2, bx1:bx2] = blended.astype(np.uint8)
    return result


# ── Bbox 平滑 ──────────────────────────────────────

def _smooth_bbox(
    buf: deque,
    bbox: Tuple[float, float, float, float],
) -> Tuple[int, int, int, int]:
    """
    将新 bbox 加入滑动窗口，返回平均后的整数 bbox。
    有效抑制检测结果的帧间抖动。
    """
    buf.append(bbox)
    return (
        int(np.mean([b[0] for b in buf])),
        int(np.mean([b[1] for b in buf])),
        int(np.mean([b[2] for b in buf])),
        int(np.mean([b[3] for b in buf])),
    )


# ── 主函数 ─────────────────────────────────────────

def replace_head(
    video_path: str,
    pig_path: str,
    output_path: str,
    head_scale: float = CARTOON_HEAD_SCALE,
    y_offset_ratio: float = 0.25,
    smooth_window: int = 5,
    white_thresh: int = CARTOON_HEAD_WHITE_THRESH,
    keep_audio: bool = True,
    ffmpeg_params: Optional[List[str]] = None,
    detect_interval: int = 30,  # detect_once=False 时生效：每 N 帧检测一次
    detect_once: bool = True,   # 数字人固定机位，仅首帧检测一次，大幅加速
) -> str:
    """
    用卡通头部视频替换原视频中的人脸区域。

    参数：
        video_path      : 原始人物视频路径
        pig_path        : 卡通头部视频路径（白色背景 MP4）
        output_path     : 输出 MP4 路径
        head_scale      : 卡通头相对人脸 bbox 的缩放倍数（默认从 config.py 读取）
                          （需要比脸大，才能盖住头发和额头）
        y_offset_ratio  : 卡通头中心相对 bbox 中心的上移比例，默认 0.25
                          （头顶占头部更多比例，需要往上偏）
        smooth_window   : bbox 平滑窗口大小，默认 5 帧
        white_thresh    : 白色背景阈值，默认 240
        keep_audio      : 是否保留原视频音频，默认 True
        detect_interval : 每 N 帧检测一次人脸（中间帧复用上次 bbox），默认 5，可显著加速

    返回：
        output_path
    """
    check_video_path(video_path)
    check_video_path(pig_path)
    ensure_output_dir(output_path)

    logger.info("加载视频 — 原始：%s，猪头：%s", video_path, pig_path)

    src_cap = cv2.VideoCapture(video_path)
    pig_cap = cv2.VideoCapture(pig_path)

    src_w  = int(src_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h  = int(src_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    src_fps = src_cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(src_cap.get(cv2.CAP_PROP_FRAME_COUNT))
    pig_total = int(pig_cap.get(cv2.CAP_PROP_FRAME_COUNT))

    logger.info("原始视频：%dx%d, %.1ffps, %d帧", src_w, src_h, src_fps, total_frames)
    logger.info("猪头视频：%d帧，将循环使用", pig_total)

    # 预加载猪头视频所有帧到内存（避免每帧重复读取和解码）
    logger.info("预加载猪头视频帧...")
    pig_frames = []
    pig_cap_all = cv2.VideoCapture(pig_path)
    while True:
        ret, frame = pig_cap_all.read()
        if not ret:
            break
        pig_frames.append(frame)
    pig_cap_all.release()
    pig_total = len(pig_frames)
    logger.info("猪头视频预加载完成：%d 帧", pig_total)

    # 预计算猪头的 BGRA 版本（白色背景去除后），根据不同的缩放尺寸缓存
    pig_bgra_cache = {}  # size -> bgra

    # 临时文件保存无音频的处理结果（后续用 moviepy 附回音频）
    tmp_path = output_path.replace(".mp4", "_tmp_noaudio.mp4")
    # 使用 mp4v 编码器，兼容性更好
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(tmp_path, fourcc, src_fps, (src_w, src_h))

    # 初始化 OpenCV 人脸检测器（Haar 级联，内置于 OpenCV，无需额外下载）
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    logger.info("人脸检测器已加载（OpenCV Haar Cascade）")

    bbox_buf = deque(maxlen=smooth_window)  # bbox 平滑缓冲
    last_bbox = None                         # 检测失败时复用上一帧结果
    pig_idx = 0                              # 猪头视频当前帧索引

    logger.info("开始逐帧处理...")
    frame_idx = 0

    while True:
        ret, src_frame = src_cap.read()
        if not ret:
            break

        # ── 取猪头当前帧（从预加载的帧数组中循环获取，避免重复IO） ─────
        pig_frame = pig_frames[pig_idx % pig_total]
        pig_idx += 1

        # ── 人脸检测 ─────────────────────────────────────────────────────
        # detect_once=True（数字人固定机位）：仅首帧检测一次，后续全复用，大幅加速
        # detect_once=False：每 detect_interval 帧检测一次
        should_detect = (
            (detect_once and last_bbox is None) or
            (not detect_once and frame_idx % detect_interval == 0)
        )
        if should_detect:
            gray = cv2.cvtColor(src_frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.15,
                minNeighbors=5,
                minSize=(80, 80),
            )
            if len(faces) > 0:
                faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                fx, fy, fw, fh = faces_sorted[0]
                last_bbox = _smooth_bbox(bbox_buf, (fx, fy, fw, fh))
                if detect_once:
                    logger.info("首帧检测完成，人脸位置已固定，后续帧直接复用（大幅加速）")

        # ── 猪头缩放 & 定位 ───────────────────────────────
        if last_bbox is not None:
            fx, fy, fw, fh = last_bbox

            # 目标尺寸：比人脸大 head_scale 倍
            target_size = int(fw * head_scale)
            if target_size > 0 and pig_frame is not None:
                # 使用缓存的 BGRA 帧（避免每帧重复处理白色背景）
                if target_size not in pig_bgra_cache:
                    pig_resized = cv2.resize(pig_frame, (target_size, target_size))
                    pig_bgra_cache[target_size] = _remove_white_bg(pig_resized, white_thresh)
                pig_bgra = pig_bgra_cache[target_size]

                # 定位：以人脸 bbox 中心为基准，向上偏移
                cx = fx + fw // 2
                cy = fy + fh // 2 - int(fh * y_offset_ratio)

                px = cx - target_size // 2
                py = cy - target_size // 2

                src_frame = _alpha_blend(src_frame, pig_bgra, px, py)

        writer.write(src_frame)
        frame_idx += 1

        if frame_idx % 100 == 0:
            logger.info("处理进度：%d / %d 帧 (%.1f%%)",
                        frame_idx, total_frames, frame_idx / total_frames * 100)

    # 释放资源
    src_cap.release()
    pig_cap.release()
    writer.release()

    logger.info("帧处理完成，共 %d 帧", frame_idx)

    # ── 附回原始音频 ──────────────────────────────────────
    if keep_audio:
        logger.info("附回原始音频（FFmpeg 方式）...")
        # 使用 FFmpeg 直接合并，避免 moviepy 二次编码
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", tmp_path, "-i", video_path,
                "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0",
                "-shortest", "-c:a", "aac", output_path
            ], check=True, capture_output=True)
            logger.info("FFmpeg 音频附加完成")
        except subprocess.CalledProcessError as e:
            logger.warning("FFmpeg 附加音频失败，回退 moviepy: %s", e)
            from moviepy import VideoFileClip
            processed = VideoFileClip(tmp_path)
            original = VideoFileClip(video_path)

            if original.audio is not None:
                final = processed.with_audio(original.audio)
            else:
                logger.warning("原视频无音频，跳过音频附加")
                final = processed

            write_kw = dict(codec="libx264", audio_codec="aac", logger="bar")
            if ffmpeg_params:
                write_kw["ffmpeg_params"] = ffmpeg_params
            final.write_videofile(output_path, **write_kw)
            final.close()
            processed.close()
            original.close()

        # 清理临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    else:
        os.rename(tmp_path, output_path)

    logger.info("头部替换完成，输出：%s", output_path)
    return output_path
