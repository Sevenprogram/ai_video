"""
音频替换模块：支持完全替换音轨和混音两种模式
"""
import logging
from typing import Optional

from moviepy import AudioFileClip, CompositeAudioClip, VideoFileClip, afx

from .utils import check_audio_path, check_video_path, ensure_output_dir

logger = logging.getLogger(__name__)


def replace_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    loop_audio: bool = True,
    audio_volume: float = 1.0,
) -> str:
    """
    完全替换视频音轨（原始音频会被丢弃）。

    参数：
        video_path   : 原始视频路径
        audio_path   : 新音频路径（mp3/wav/aac 等）
        output_path  : 输出 MP4 路径
        loop_audio   : 音频时长 < 视频时长时是否循环填充，默认 True
        audio_volume : 新音频音量倍数，1.0 为原始音量，默认 1.0

    返回：
        output_path
    """
    check_video_path(video_path)
    check_audio_path(audio_path)
    ensure_output_dir(output_path)

    logger.info("加载视频：%s", video_path)
    video_clip = VideoFileClip(video_path)
    logger.info("加载音频：%s", audio_path)
    audio_clip = AudioFileClip(audio_path)

    video_duration = video_clip.duration
    audio_duration = audio_clip.duration
    logger.info("视频时长：%.2fs，音频时长：%.2fs", video_duration, audio_duration)

    # 处理音频与视频时长不一致的情况
    if audio_duration < video_duration:
        if loop_audio:
            # 循环音频直到填满视频时长
            logger.info("音频较短（%.2fs < %.2fs），循环填充", audio_duration, video_duration)
            audio_clip = afx.AudioLoop(duration=video_duration).apply(audio_clip)
        else:
            # 不循环时，不足部分由 moviepy 自动静音处理
            logger.warning("音频较短（%.2fs < %.2fs），不足部分将静音", audio_duration, video_duration)
    elif audio_duration > video_duration:
        # 裁剪多余的音频部分
        logger.info("音频较长（%.2fs > %.2fs），截断至视频时长", audio_duration, video_duration)
        audio_clip = audio_clip.subclipped(0, video_duration)

    # 按需调整音量
    if abs(audio_volume - 1.0) > 0.001:
        logger.debug("调整音量：%.2f 倍", audio_volume)
        audio_clip = audio_clip.with_multiply_volume(audio_volume)

    # 将新音频绑定到视频（替换原音轨）
    final = video_clip.with_audio(audio_clip)

    logger.info("导出至：%s", output_path)
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=video_clip.fps,
        logger="bar",
    )

    # 释放资源
    final.close()
    video_clip.close()
    audio_clip.close()

    logger.info("音频替换完成，输出文件：%s", output_path)
    return output_path


def mix_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    original_volume: float = 1.0,
    new_audio_volume: float = 1.0,
    loop_audio: bool = True,
) -> str:
    """
    混音：保留原始音轨并叠加新音频（可分别调节两路音量）。

    参数：
        video_path       : 原始视频路径
        audio_path       : 新增音频路径
        output_path      : 输出 MP4 路径
        original_volume  : 原始音轨音量倍数，默认 1.0
        new_audio_volume : 新音频音量倍数，默认 1.0
        loop_audio       : 新音频时长不足时是否循环，默认 True

    返回：
        output_path
    """
    check_video_path(video_path)
    check_audio_path(audio_path)
    ensure_output_dir(output_path)

    logger.info("加载视频：%s", video_path)
    video_clip = VideoFileClip(video_path)
    logger.info("加载新音频：%s", audio_path)
    new_audio = AudioFileClip(audio_path)

    video_duration = video_clip.duration
    logger.info("视频时长：%.2fs，新音频时长：%.2fs", video_duration, new_audio.duration)

    # 对齐新音频时长与视频时长
    if new_audio.duration < video_duration:
        if loop_audio:
            logger.info("新音频较短，循环填充至 %.2fs", video_duration)
            new_audio = afx.AudioLoop(duration=video_duration).apply(new_audio)
        else:
            logger.warning("新音频较短（%.2fs），不足部分将静音", new_audio.duration)
    elif new_audio.duration > video_duration:
        logger.info("新音频较长，截断至视频时长 %.2fs", video_duration)
        new_audio = new_audio.subclipped(0, video_duration)

    # 按需调整原始音轨音量
    if abs(original_volume - 1.0) > 0.001 and video_clip.audio is not None:
        logger.debug("调整原始音轨音量：%.2f 倍", original_volume)
        original_audio = video_clip.audio.with_multiply_volume(original_volume)
    else:
        original_audio = video_clip.audio

    # 按需调整新音频音量
    if abs(new_audio_volume - 1.0) > 0.001:
        logger.debug("调整新音频音量：%.2f 倍", new_audio_volume)
        new_audio = new_audio.with_multiply_volume(new_audio_volume)

    # 混音合成：两路音频叠加
    if original_audio is not None:
        logger.info("混音：原始音轨 × %.2f + 新音频 × %.2f", original_volume, new_audio_volume)
        mixed = CompositeAudioClip([original_audio, new_audio])
    else:
        # 原视频没有音轨，直接使用新音频
        logger.warning("原视频无音频，将直接使用新音频")
        mixed = new_audio

    final = video_clip.with_audio(mixed)

    logger.info("导出至：%s", output_path)
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=video_clip.fps,
        logger="bar",
    )

    # 释放资源
    final.close()
    video_clip.close()
    new_audio.close()

    logger.info("混音完成，输出文件：%s", output_path)
    return output_path
