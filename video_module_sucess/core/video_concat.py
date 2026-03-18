"""
视频顺序拼接模块：将多个视频首尾相连合并为一个视频
"""
import logging
from typing import List, Optional, Tuple

from moviepy import VideoFileClip, concatenate_videoclips

from .utils import check_video_path, ensure_output_dir, normalize_clip

logger = logging.getLogger(__name__)


def concat_videos(
    video_paths: List[str],
    output_path: str,
    target_size: Optional[Tuple[int, int]] = None,
    target_fps: Optional[float] = None,
    keep_audio: bool = True,
    method: str = "compose",
) -> str:
    """
    将多个视频顺序拼接为一个 MP4 文件。

    参数：
        video_paths : 视频文件路径列表，按顺序拼接，至少 2 个
        output_path : 输出 MP4 路径
        target_size : 目标分辨率 (width, height)，None 则以第一个视频为准
        target_fps  : 目标帧率，None 则以第一个视频为准
        keep_audio  : 是否保留原始音频，默认 True
        method      : moviepy 拼接模式，'compose'（推荐）或 'chain'

    返回：
        output_path
    """
    if len(video_paths) < 2:
        raise ValueError(f"至少需要 2 个视频才能拼接，当前只有 {len(video_paths)} 个")

    logger.info("开始拼接，共 %d 个视频", len(video_paths))

    # 校验所有输入路径
    for p in video_paths:
        check_video_path(p)

    ensure_output_dir(output_path)

    # 一次性加载所有片段
    clips = [VideoFileClip(p) for p in video_paths]
    logger.debug("所有视频已加载")

    # 以第一个视频的参数作为基准（未指定时）
    if target_size is None:
        target_size = clips[0].size
    if target_fps is None:
        target_fps = clips[0].fps

    logger.info("目标规格 — 分辨率: %s，帧率: %.2f fps", target_size, target_fps)

    # 逐个标准化分辨率和帧率
    normalized = []
    for i, clip in enumerate(clips):
        logger.info("处理 [%d/%d]：%s（原尺寸 %s，%.2f fps）",
                    i + 1, len(clips), video_paths[i], clip.size, clip.fps)
        c = normalize_clip(clip, target_size, target_fps)
        if not keep_audio:
            c = c.without_audio()
            logger.debug("已移除音频：%s", video_paths[i])
        normalized.append(c)

    # 拼接所有标准化后的片段
    logger.info("开始拼接 %d 个片段（method=%s）...", len(normalized), method)
    final = concatenate_videoclips(normalized, method=method)
    logger.debug("拼接完成，总时长 %.2f 秒", final.duration)

    # 编码导出
    logger.info("导出至：%s", output_path)
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=target_fps,
        logger="bar",
    )

    # 释放所有 clip 资源，避免内存泄漏
    final.close()
    for c in clips:
        c.close()

    logger.info("拼接完成，输出文件：%s", output_path)
    return output_path
