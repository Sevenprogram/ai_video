"""
视频合成与音频替换对外接口模块

其他程序调用示例：
    from synthesis import concat, overlay, replace_audio, mix_audio, video_info

日志控制示例（调用方可按需设置）：
    import logging
    logging.basicConfig(level=logging.INFO)          # 显示 INFO 及以上
    logging.basicConfig(level=logging.DEBUG)         # 显示所有调试信息
    logging.getLogger("core").setLevel(logging.WARNING)  # 只看警告和错误
"""
import argparse
import logging
from typing import List, Optional, Tuple

# 默认日志配置：仅在直接运行本模块时生效，被 import 时由调用方控制
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)

from core.utils import get_video_info
from core.video_concat import concat_videos
from core.video_overlay import overlay_video
from core.audio_replace import replace_audio as _replace_audio
from core.audio_replace import mix_audio as _mix_audio
from core.head_replace import replace_head as _replace_head

__all__ = ["concat", "overlay", "replace_audio", "mix_audio", "video_info", "replace_head"]


# ─────────────────────────────────────────────
# 对外公开函数
# ─────────────────────────────────────────────

def concat(
    video_paths: List[str],
    output_path: str,
    target_size: Optional[Tuple[int, int]] = None,
    target_fps: Optional[float] = None,
    keep_audio: bool = True,
) -> str:
    """
    顺序拼接多个视频。

    参数：
        video_paths  : 视频路径列表，按顺序拼接，至少 2 个
        output_path  : 输出 MP4 路径
        target_size  : 目标分辨率 (width, height)，None 则以第一个视频为准
        target_fps   : 目标帧率，None 则以第一个视频为准
        keep_audio   : 是否保留原始音频，默认 True

    返回：
        输出文件路径

    调用示例：
        from synthesis import concat
        concat(
            video_paths=[r"C:\videos\a.mp4", r"C:\videos\b.mp4"],
            output_path=r"C:\output\result.mp4",
        )
    """
    return concat_videos(
        video_paths=video_paths,
        output_path=output_path,
        target_size=target_size,
        target_fps=target_fps,
        keep_audio=keep_audio,
    )


def overlay(
    main_path: str,
    sub_path: str,
    output_path: str,
    position: str = "bottom-right",
    sub_scale: float = 0.25,
    opacity: float = 1.0,
    margin: int = 20,
    sub_start: float = 0.0,
    sub_end: Optional[float] = None,
    main_audio: bool = True,
    sub_audio: bool = False,
    sub_crop: Optional[Tuple[int, int, int, int]] = None,
    target_duration: Optional[float] = None,
    ffmpeg_params: Optional[list] = None,
) -> str:
    """
    画中画：将子视频叠加到主视频上。

    参数：
        main_path  : 主视频路径（背景大视频）
        sub_path   : 子视频路径（小窗视频）
        output_path: 输出 MP4 路径
        position   : 小窗位置，可选值：
                     'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
                     | 'center' | 'top-center' | 'bottom-center'
                     默认 'bottom-right'
        sub_scale  : 小窗宽度占主视频宽度比例，默认 0.25（即 25%）
        opacity    : 小窗透明度 0.0~1.0，默认 1.0（不透明）
        margin     : 小窗距边缘像素，默认 20
        sub_start  : 小窗出现的起始时间（秒），默认 0
        sub_end    : 小窗消失的时间（秒），None 表示持续到主视频结束
        main_audio : 是否保留主视频音频，默认 True
        sub_audio  : 是否叠加小窗视频音频，默认 False
        sub_crop   : 裁剪子视频白边 (x1, y1, x2, y2)，None 表示不裁剪
                     例如 (616, 0, 1303, 1080) 可去掉 1920x1080 素材的左右白边

    返回：
        输出文件路径

    调用示例：
        from synthesis import overlay
        overlay(
            main_path=r"C:\videos\main.mp4",
            sub_path=r"C:\videos\cam.mp4",
            output_path=r"C:\output\pip.mp4",
            position="bottom-right",
            sub_scale=0.3,
            sub_crop=(616, 0, 1303, 1080),
        )
    """
    return overlay_video(
        main_path=main_path,
        sub_path=sub_path,
        output_path=output_path,
        position=position,
        sub_scale=sub_scale,
        opacity=opacity,
        margin=margin,
        sub_start=sub_start,
        sub_end=sub_end,
        main_audio=main_audio,
        sub_audio=sub_audio,
        sub_crop=sub_crop,
        target_duration=target_duration,
        ffmpeg_params=ffmpeg_params,
    )


def replace_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    loop_audio: bool = True,
    audio_volume: float = 1.0,
    trim_to_audio: bool = False,
    ffmpeg_params: Optional[list] = None,
) -> str:
    """
    完全替换视频音轨。

    参数：
        video_path     : 视频路径
        audio_path     : 新音频路径（mp3/wav/aac 等）
        output_path    : 输出 MP4 路径
        loop_audio     : 音频时长不足时是否循环，默认 True
        audio_volume   : 音量倍数，1.0 为原始音量，默认 1.0
        trim_to_audio  : True 时以音频为时长基准，视频裁剪或延长
        ffmpeg_params  : FFmpeg 额外参数

    返回：
        输出文件路径
    """
    return _replace_audio(
        video_path=video_path,
        audio_path=audio_path,
        output_path=output_path,
        loop_audio=loop_audio,
        audio_volume=audio_volume,
        trim_to_audio=trim_to_audio,
        ffmpeg_params=ffmpeg_params,
    )


def mix_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    original_volume: float = 1.0,
    new_audio_volume: float = 1.0,
    loop_audio: bool = True,
) -> str:
    """
    混音：保留原始音轨并叠加新音频。

    参数：
        video_path       : 视频路径
        audio_path       : 新增音频路径
        output_path      : 输出 MP4 路径
        original_volume  : 原始音轨音量倍数，默认 1.0
        new_audio_volume : 新音频音量倍数，默认 1.0
        loop_audio       : 新音频时长不足时是否循环，默认 True

    返回：
        输出文件路径

    调用示例：
        from synthesis import mix_audio
        mix_audio(
            video_path=r"C:\videos\video.mp4",
            audio_path=r"C:\audios\bgm.mp3",
            output_path=r"C:\output\mixed.mp4",
            original_volume=0.8,
            new_audio_volume=0.5,
        )
    """
    return _mix_audio(
        video_path=video_path,
        audio_path=audio_path,
        output_path=output_path,
        original_volume=original_volume,
        new_audio_volume=new_audio_volume,
        loop_audio=loop_audio,
    )


def replace_head(
    video_path: str,
    pig_path: str,
    output_path: str,
    head_scale: float = 10,
    y_offset_ratio: float = 0.25,
    smooth_window: int = 5,
    white_thresh: int = 240,
    keep_audio: bool = True,
    ffmpeg_params: Optional[list] = None,
    detect_interval: int = 30,
    detect_once: bool = True,
) -> str:
    """
    用卡通头部视频替换原视频中的人脸区域。

    参数：
        video_path      : 原始人物视频路径
        pig_path        : 卡通头部视频路径（白色背景 MP4）
        output_path     : 输出 MP4 路径
        head_scale      : 卡通头相对人脸大小的缩放倍数，默认 1.8
        y_offset_ratio  : 卡通头中心向上偏移比例，默认 0.25
        smooth_window   : bbox 平滑窗口帧数，防抖动，默认 5
        white_thresh    : 白色背景抠图阈值（0~255），默认 240
        keep_audio      : 是否保留原视频音频，默认 True

    返回：
        输出文件路径

    调用示例：
        from synthesis import replace_head
        replace_head(
            video_path=r"action_clips/idle_hands_open.mp4",
            pig_path=r"action_clips/pig.mp4",
            output_path=r"output/pig_head.mp4",
        )
    """
    return _replace_head(
        video_path=video_path,
        pig_path=pig_path,
        output_path=output_path,
        head_scale=head_scale,
        y_offset_ratio=y_offset_ratio,
        smooth_window=smooth_window,
        white_thresh=white_thresh,
        keep_audio=keep_audio,
        ffmpeg_params=ffmpeg_params,
        detect_interval=detect_interval,
        detect_once=detect_once,
    )


def video_info(video_path: str) -> dict:
    """
    获取视频基本信息。

    参数：
        video_path : 视频路径

    返回：
        dict，包含 path / duration / fps / size / has_audio

    调用示例：
        from synthesis import video_info
        info = video_info(r"C:\videos\video.mp4")
        print(info)
        # {'path': '...', 'duration': 12.5, 'fps': 30.0, 'size': (1920, 1080), 'has_audio': True}
    """
    return get_video_info(video_path)


# ─────────────────────────────────────────────
# 命令行入口（直接运行 python synthesis.py --help）
# ─────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="视频合成与音频替换工具",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # concat
    p = subparsers.add_parser("concat", help="顺序拼接多个视频")
    p.add_argument("videos", nargs="+", help="输入视频路径列表（按顺序）")
    p.add_argument("-o", "--output", required=True, help="输出 MP4 路径")
    p.add_argument("--no-audio", action="store_true", help="去除所有音频")
    p.add_argument("--width", type=int, help="目标宽度（像素）")
    p.add_argument("--height", type=int, help="目标高度（像素）")
    p.add_argument("--fps", type=float, help="目标帧率")

    # overlay
    p = subparsers.add_parser("overlay", help="画中画：子视频叠加到主视频")
    p.add_argument("main", help="主视频路径")
    p.add_argument("sub", help="子视频路径")
    p.add_argument("-o", "--output", required=True, help="输出 MP4 路径")
    p.add_argument("--position", default="bottom-right",
                   choices=["top-left", "top-right", "bottom-left", "bottom-right",
                            "center", "top-center", "bottom-center"])
    p.add_argument("--scale", type=float, default=0.25, help="小窗缩放比例，默认 0.25")
    p.add_argument("--opacity", type=float, default=1.0, help="小窗透明度 0~1，默认 1.0")
    p.add_argument("--margin", type=int, default=20, help="距边缘像素，默认 20")
    p.add_argument("--no-main-audio", action="store_true", help="去除主视频音频")
    p.add_argument("--sub-audio", action="store_true", help="叠加小窗视频音频")

    # replace-audio
    p = subparsers.add_parser("replace-audio", help="完全替换视频音轨")
    p.add_argument("video", help="视频路径")
    p.add_argument("audio", help="新音频路径")
    p.add_argument("-o", "--output", required=True, help="输出 MP4 路径")
    p.add_argument("--no-loop", action="store_true", help="音频不足时不循环")
    p.add_argument("--volume", type=float, default=1.0, help="音量倍数，默认 1.0")

    # mix-audio
    p = subparsers.add_parser("mix-audio", help="混音：保留原音轨并叠加新音频")
    p.add_argument("video", help="视频路径")
    p.add_argument("audio", help="新音频路径")
    p.add_argument("-o", "--output", required=True, help="输出 MP4 路径")
    p.add_argument("--orig-vol", type=float, default=1.0, help="原始音轨音量，默认 1.0")
    p.add_argument("--new-vol", type=float, default=1.0, help="新音频音量，默认 1.0")
    p.add_argument("--no-loop", action="store_true", help="音频不足时不循环")

    # info
    p = subparsers.add_parser("info", help="查看视频基本信息")
    p.add_argument("video", help="视频路径")

    return parser


def _cli():
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "concat":
        target_size = (args.width, args.height) if args.width and args.height else None
        concat(args.videos, args.output, target_size=target_size,
               target_fps=args.fps, keep_audio=not args.no_audio)

    elif args.command == "overlay":
        overlay(args.main, args.sub, args.output,
                position=args.position, sub_scale=args.scale,
                opacity=args.opacity, margin=args.margin,
                main_audio=not args.no_main_audio, sub_audio=args.sub_audio)

    elif args.command == "replace-audio":
        replace_audio(args.video, args.audio, args.output,
                      loop_audio=not args.no_loop, audio_volume=args.volume)

    elif args.command == "mix-audio":
        mix_audio(args.video, args.audio, args.output,
                  original_volume=args.orig_vol, new_audio_volume=args.new_vol,
                  loop_audio=not args.no_loop)

    elif args.command == "info":
        info = video_info(args.video)
        print("\n=== 视频信息 ===")
        for k, v in info.items():
            print(f"  {k:12s}: {v}")


if __name__ == "__main__":
    _cli()
