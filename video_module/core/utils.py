"""
工具函数：视频/音频格式校验、分辨率标准化、视频信息读取
"""
import logging
import os

from moviepy import ColorClip, CompositeVideoClip, VideoFileClip

logger = logging.getLogger(__name__)

# 支持的视频/音频扩展名白名单
SUPPORTED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv"}
SUPPORTED_AUDIO_EXT = {".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac"}


def check_video_path(path: str) -> str:
    """
    校验视频文件路径合法性。
    - 文件必须存在
    - 扩展名必须在白名单内
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"视频文件不存在：{path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_VIDEO_EXT:
        raise ValueError(f"不支持的视频格式 '{ext}'，支持：{SUPPORTED_VIDEO_EXT}")
    logger.debug("视频路径校验通过：%s", path)
    return path


def check_audio_path(path: str) -> str:
    """
    校验音频文件路径合法性。
    - 文件必须存在
    - 扩展名必须在白名单内
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"音频文件不存在：{path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_AUDIO_EXT:
        raise ValueError(f"不支持的音频格式 '{ext}'，支持：{SUPPORTED_AUDIO_EXT}")
    logger.debug("音频路径校验通过：%s", path)
    return path


def ensure_output_dir(output_path: str) -> None:
    """确保输出文件的父目录存在，不存在时自动创建"""
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    logger.debug("输出目录已就绪：%s", output_dir)


def normalize_clip(clip: VideoFileClip, target_size: tuple, target_fps: float) -> VideoFileClip:
    """
    将视频片段标准化到指定分辨率和帧率。

    分辨率处理策略：
      - 宽高比相近（误差 < 1%）→ 直接缩放
      - 宽高比差异较大 → 等比缩放后居中放置，四周补黑边

    帧率处理策略：
      - 帧率误差 > 0.01fps 时才做转换，避免不必要的重编码
    """
    w, h = target_size

    if clip.size != (w, h):
        clip_ratio = clip.w / clip.h
        target_ratio = w / h

        if abs(clip_ratio - target_ratio) < 0.01:
            # 宽高比接近，直接拉伸到目标尺寸
            logger.debug("分辨率不一致，直接缩放 %s → %s", clip.size, (w, h))
            clip = clip.resized((w, h))
        else:
            # 宽高比差异较大：先等比缩放，再加黑边居中
            logger.debug(
                "宽高比不匹配（原 %.3f，目标 %.3f），等比缩放后补黑边",
                clip_ratio, target_ratio,
            )
            if clip_ratio > target_ratio:
                # 原视频更"宽"，以高度为基准缩放，左右留空
                clip = clip.resized(height=h)
            else:
                # 原视频更"高"，以宽度为基准缩放，上下留空
                clip = clip.resized(width=w)

            # 黑色背景画布，与目标尺寸一致
            bg = ColorClip(size=(w, h), color=(0, 0, 0), duration=clip.duration)
            x_offset = (w - clip.w) // 2
            y_offset = (h - clip.h) // 2
            logger.debug("黑边偏移量：x=%d, y=%d", x_offset, y_offset)
            clip = CompositeVideoClip([bg, clip.with_position((x_offset, y_offset))])

    if abs(clip.fps - target_fps) > 0.01:
        logger.debug("帧率不一致，转换 %.2f → %.2f fps", clip.fps, target_fps)
        clip = clip.with_fps(target_fps)

    return clip


def get_video_info(path: str) -> dict:
    """
    读取并返回视频基本信息。

    返回字段：
        path      : 文件路径
        duration  : 时长（秒，保留 3 位小数）
        fps       : 帧率
        size      : 分辨率 (width, height)
        has_audio : 是否含音轨
    """
    check_video_path(path)
    logger.debug("读取视频信息：%s", path)
    clip = VideoFileClip(path)
    info = {
        "path": path,
        "duration": round(clip.duration, 3),
        "fps": clip.fps,
        "size": clip.size,
        "has_audio": clip.audio is not None,
    }
    clip.close()
    logger.info("视频信息：%s", info)
    return info
