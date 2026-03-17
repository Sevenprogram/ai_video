"""
画中画模块：将子视频叠加到主视频上（支持位置、大小、透明度、出现时段调节）
"""
import logging
from typing import Literal, Optional, Tuple

from moviepy import CompositeVideoClip, VideoFileClip

from .utils import check_video_path, ensure_output_dir

logger = logging.getLogger(__name__)

# 位置预设类型
PositionPreset = Literal[
    "top-left", "top-right", "bottom-left", "bottom-right",
    "center", "top-center", "bottom-center",
]

# 各位置预设对应的坐标计算函数
# 参数：主视频宽/高、子视频宽/高、边距
POSITION_MAP = {
    "top-left":      lambda mw, mh, sw, sh, mg: (mg, mg),
    "top-right":     lambda mw, mh, sw, sh, mg: (mw - sw - mg, mg),
    "bottom-left":   lambda mw, mh, sw, sh, mg: (mg, mh - sh - mg),
    "bottom-right":  lambda mw, mh, sw, sh, mg: (mw - sw - mg, mh - sh - mg),
    "center":        lambda mw, mh, sw, sh, mg: ((mw - sw) // 2, (mh - sh) // 2),
    "top-center":    lambda mw, mh, sw, sh, mg: ((mw - sw) // 2, mg),
    "bottom-center": lambda mw, mh, sw, sh, mg: ((mw - sw) // 2, mh - sh - mg),
}


def overlay_video(
    main_path: str,
    sub_path: str,
    output_path: str,
    position: PositionPreset = "bottom-right",
    sub_scale: float = 0.25,
    opacity: float = 1.0,
    margin: int = 20,
    sub_start: float = 0.0,
    sub_end: Optional[float] = None,
    main_audio: bool = True,
    sub_audio: bool = False,
    sub_crop: Optional[Tuple[int, int, int, int]] = None,
) -> str:
    """
    将子视频以画中画方式叠加到主视频上。

    参数：
        main_path  : 主视频路径（背景大视频）
        sub_path   : 子视频路径（小窗）
        output_path: 输出 MP4 路径
        position   : 小窗位置预设（见 POSITION_MAP）
        sub_scale  : 小窗宽度占主视频宽度比例，默认 0.25
        opacity    : 小窗透明度 0.0~1.0，默认 1.0（不透明）
        margin     : 小窗距画面边缘的像素间距，默认 20px
        sub_start  : 小窗在主视频时间轴上的起始时间（秒），默认 0
        sub_end    : 小窗消失时间（秒），None 表示持续到主视频结束
        main_audio : 是否保留主视频音频，默认 True
        sub_audio  : 是否叠加小窗视频音频，默认 False
        sub_crop   : 裁剪子视频白边，格式 (x1, y1, x2, y2)，None 表示不裁剪
                     例如 (616, 0, 1303, 1080) 可去掉左右白边只保留人物区域

    返回：
        output_path
    """
    check_video_path(main_path)
    check_video_path(sub_path)
    ensure_output_dir(output_path)

    logger.info("加载视频 — 主：%s，子：%s", main_path, sub_path)
    main_clip = VideoFileClip(main_path)
    sub_clip = VideoFileClip(sub_path)

    # 裁剪子视频（去除白边），必须在缩放前做，避免影响比例计算
    if sub_crop is not None:
        x1, y1, x2, y2 = sub_crop
        logger.info("裁剪子视频白边：x1=%d, y1=%d, x2=%d, y2=%d", x1, y1, x2, y2)
        sub_clip = sub_clip.cropped(x1=x1, y1=y1, x2=x2, y2=y2)

    main_w, main_h = main_clip.size

    # 子视频目标尺寸：宽度按比例缩放，高度保持裁剪后的宽高比
    sub_w = int(main_w * sub_scale)
    sub_h = int(sub_w * sub_clip.h / sub_clip.w)
    logger.info(
        "主视频尺寸：%s，子视频缩放至：(%d, %d)（scale=%.2f）",
        main_clip.size, sub_w, sub_h, sub_scale,
    )

    # 缩放子视频到目标尺寸
    sub_clip = sub_clip.resized((sub_w, sub_h))

    # 设置透明度（仅在非完全不透明时处理，避免不必要的 alpha 计算）
    if opacity < 1.0:
        logger.debug("设置子视频透明度：%.2f", opacity)
        sub_clip = sub_clip.with_effects([lambda c: c.with_opacity(opacity)])

    # 根据位置预设计算小窗左上角坐标
    pos_func = POSITION_MAP.get(position)
    if pos_func is None:
        raise ValueError(f"不支持的 position 值：'{position}'，可选：{list(POSITION_MAP.keys())}")
    pos_x, pos_y = pos_func(main_w, main_h, sub_w, sub_h, margin)
    logger.info("小窗位置：%s → 坐标 (%d, %d)，边距 %dpx", position, pos_x, pos_y, margin)

    # 限制子视频的显示时段，不能超过主视频时长
    actual_end = min(sub_end if sub_end is not None else main_clip.duration, main_clip.duration)
    logger.debug("子视频显示时段：%.2fs ~ %.2fs", sub_start, actual_end)
    sub_clip = sub_clip.with_start(sub_start).with_end(actual_end)
    sub_clip = sub_clip.with_position((pos_x, pos_y))

    # 音频处理
    if not main_audio:
        logger.debug("已移除主视频音频")
        main_clip = main_clip.without_audio()
    if not sub_audio:
        logger.debug("已移除子视频音频")
        sub_clip = sub_clip.without_audio()

    # 合成：主视频在底层，子视频叠加在上层
    logger.info("开始合成画中画...")
    final = CompositeVideoClip([main_clip, sub_clip], size=(main_w, main_h))
    final = final.with_duration(main_clip.duration)

    logger.info("导出至：%s", output_path)
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=main_clip.fps,
        logger="bar",
    )

    # 释放资源
    final.close()
    main_clip.close()
    sub_clip.close()

    logger.info("画中画合成完成，输出文件：%s", output_path)
    return output_path
