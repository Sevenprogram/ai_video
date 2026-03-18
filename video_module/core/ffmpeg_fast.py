"""
FFmpeg 快速路径：用于 Step 1 拼接、Step 2 替换音频、Step 4 画中画。
相比 MoviePy 解码到 Python 再编码，FFmpeg 原生 filter 可显著加速。
"""
import logging
import shutil
import subprocess
from typing import List, Optional, Tuple

from .utils import check_audio_path, check_video_path, ensure_output_dir

logger = logging.getLogger(__name__)

POSITION_MAP = {
    "top-left": lambda mw, mh, sw, sh, mg: (mg, mg),
    "top-right": lambda mw, mh, sw, sh, mg: (mw - sw - mg, mg),
    "bottom-left": lambda mw, mh, sw, sh, mg: (mg, mh - sh - mg),
    "bottom-right": lambda mw, mh, sw, sh, mg: (mw - sw - mg, mh - sh - mg),
    "center": lambda mw, mh, sw, sh, mg: ((mw - sw) // 2, (mh - sh) // 2),
    "top-center": lambda mw, mh, sw, sh, mg: ((mw - sw) // 2, mg),
    "bottom-center": lambda mw, mh, sw, sh, mg: ((mw - sw) // 2, mh - sh - mg),
}


def _ffmpeg_available() -> bool:
    """检查 ffmpeg 是否可用。"""
    return shutil.which("ffmpeg") is not None


def _run_ffmpeg(args: List[str], desc: str = "FFmpeg") -> None:
    """执行 ffmpeg 命令，失败时抛出 CalledProcessError。"""
    cmd = ["ffmpeg", "-y"] + args
    logger.debug("%s: %s", desc, " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)


def concat_and_trim(
    clip_paths: List[str],
    output_path: str,
    target_duration: float,
    ffmpeg_preset: str = "ultrafast",
) -> str:
    """
    Step 1 快速路径：FFmpeg concat filter 拼接 + trim。
    比 MoviePy 快数倍。
    """
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg 未安装或不在 PATH 中")
    for p in clip_paths:
        check_video_path(p)
    ensure_output_dir(output_path)

    n = len(clip_paths)
    if n < 1:
        raise ValueError("至少需要 1 个视频")
    if n == 1:
        # 单文件直接 trim 即可
        _run_ffmpeg([
            "-i", clip_paths[0],
            "-t", str(target_duration),
            "-c:v", "libx264", "-preset", ffmpeg_preset,
            "-c:a", "aac",
            output_path,
        ], "concat_trim(single)")
        return output_path

    # 构建 concat filter： [0:v][0:a][1:v][1:a]...concat=n:v=1:a=1[outv][outa]
    # 然后 trim 到 target_duration
    inp = []
    for p in clip_paths:
        inp.extend(["-i", p])

    # concat 后 trim
    filter_parts = []
    for i in range(n):
        filter_parts.append(f"[{i}:v][{i}:a]")
    concat_input = "".join(filter_parts)
    # trim 到 target_duration，setpts 重置时间戳
    duration_str = str(target_duration)
    filter_complex = (
        f"{concat_input}concat=n={n}:v=1:a=1[outv][outa];"
        f"[outv]trim=0:{duration_str},setpts=PTS-STARTPTS[v];"
        f"[outa]atrim=0:{duration_str},asetpts=PTS-STARTPTS[a]"
    )

    _run_ffmpeg(
        inp + ["-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-preset", ffmpeg_preset, "-c:a", "aac",
               output_path],
        "concat_trim",
    )
    logger.info("Step 1 (FFmpeg) 完成：%s", output_path)
    return output_path


def _get_media_duration(path: str, is_video: bool = True) -> Optional[float]:
    """用 ffprobe 读取音视频时长（优先 stream，否则 format）。"""
    stream = "v:0" if is_video else "a:0"
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", stream,
             "-show_entries", "stream=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True,
        )
        s = r.stdout.strip()
        if s:
            return float(s)
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True,
        )
        s = r.stdout.strip()
        return float(s) if s else None
    except Exception:
        return None


def replace_audio_fast(
    video_path: str,
    audio_path: str,
    output_path: str,
    trim_to_audio: bool = False,
    ffmpeg_preset: str = "ultrafast",
) -> Optional[str]:
    """
    Step 2 快速路径：FFmpeg 替换音轨，永不回退 MoviePy。
    - trim_to_audio=True 且视频>=音频时：-c:v copy 不重编码，极快
    - 视频<音频时：FFmpeg 截断音频至视频长度，仍走快速路径（避免 MoviePy 逐帧延长）
    """
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg 未安装或不在 PATH 中")
    check_video_path(video_path)
    check_audio_path(audio_path)
    ensure_output_dir(output_path)

    if trim_to_audio:
        v_dur = _get_media_duration(video_path, is_video=True)
        a_dur = _get_media_duration(audio_path, is_video=False)
        # 视频短于音频时：截断音频至视频长度，全用 FFmpeg，避免 MoviePy 逐帧延长
        # 视频长于音频时：用音频长度截断视频
        trimmed_audio = None
        trimmed_video = None
        
        if v_dur is not None and a_dur is not None:
            if v_dur < a_dur - 0.5:
                # 视频短于音频：截断音频
                import tempfile
                import os as _os
                fd, trimmed_audio = tempfile.mkstemp(suffix=".mp3")
                _os.close(fd)
                try:
                    _run_ffmpeg(
                        ["-i", audio_path, "-t", str(v_dur), "-acodec", "copy", trimmed_audio],
                        "trim_audio_to_video",
                    )
                    audio_path = trimmed_audio
                    a_dur = v_dur
                    logger.info("Step 2: 音频(%.1fs)截断至视频长度(%.1fs)，走 FFmpeg 快速路径", a_dur, v_dur)
                except Exception:
                    if trimmed_audio and _os.path.exists(trimmed_audio):
                        _os.remove(trimmed_audio)
                    raise
            elif v_dur > a_dur + 0.5:
                # 视频长于音频：截断视频
                import tempfile
                import os as _os
                fd, trimmed_video = tempfile.mkstemp(suffix=".mp4")
                _os.close(fd)
                try:
                    _run_ffmpeg(
                        ["-i", video_path, "-t", str(a_dur), "-c", "copy", trimmed_video],
                        "trim_video_to_audio",
                    )
                    video_path = trimmed_video
                    v_dur = a_dur
                    logger.info("Step 2: 视频(%.1fs)截断至音频长度(%.1fs)，走 FFmpeg 快速路径", v_dur, a_dur)
                except Exception:
                    if trimmed_video and _os.path.exists(trimmed_video):
                        _os.remove(trimmed_video)
                    raise
        
        try:
            # -c:v copy 不重编码，极快
            _run_ffmpeg([
                "-i", video_path, "-i", audio_path,
                "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest",
                output_path,
            ], "replace_audio(copy)")
        finally:
            if trimmed_audio:
                import os as _os
                if _os.path.exists(trimmed_audio):
                    _os.remove(trimmed_audio)
            if trimmed_video:
                import os as _os
                if _os.path.exists(trimmed_video):
                    _os.remove(trimmed_video)
    else:
        _run_ffmpeg([
            "-i", video_path, "-i", audio_path,
            "-c:v", "libx264", "-preset", ffmpeg_preset,
            "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0", "-shortest",
            output_path,
        ], "replace_audio")

    logger.info("Step 2 (FFmpeg) 完成：%s", output_path)
    return output_path


def overlay_fast(
    main_path: str,
    sub_path: str,
    output_path: str,
    position: str = "bottom-right",
    sub_scale: float = 0.18,
    margin: int = 20,
    sub_crop: Optional[Tuple[int, int, int, int]] = None,
    main_audio: bool = False,
    sub_audio: bool = True,
    target_duration: Optional[float] = None,
    ffmpeg_preset: str = "ultrafast",
) -> str:
    """
    Step 4 快速路径：FFmpeg overlay 画中画。
    主视频无音、子视频有音时，直接 overlay + 映射子视频音轨，无需 MoviePy 逐帧合成。
    """
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg 未安装或不在 PATH 中")
    check_video_path(main_path)
    check_video_path(sub_path)
    ensure_output_dir(output_path)

    # 用 ffprobe 取主视频尺寸和时长（轻量）
    main_dur = None
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration",
             "-of", "csv=p=0", main_path],
            capture_output=True, text=True, check=True,
        )
        parts = r.stdout.strip().split(",")
        main_w, main_h = int(parts[0]), int(parts[1])
        if len(parts) >= 3 and parts[2]:
            main_dur = float(parts[2])
    except Exception as e:
        logger.warning("ffprobe 读取主视频失败，回退默认 1920x1080: %s", e)
        main_w, main_h = 1920, 1080

    # 子视频目标尺寸：宽度=主视频*scale，高度按子视频宽高比
    sub_w = int(main_w * sub_scale)
    if sub_crop:
        crop_w = sub_crop[2] - sub_crop[0]
        crop_h = sub_crop[3] - sub_crop[1]
        sub_h = int(sub_w * crop_h / crop_w) if crop_w else sub_w
    else:
        # 无 crop 时用 ffprobe 取子视频尺寸
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0", sub_path],
                capture_output=True, text=True, check=True,
            )
            parts = r.stdout.strip().split(",")
            sw0, sh0 = int(parts[0]), int(parts[1])
            sub_h = int(sub_w * sh0 / sw0) if sw0 else sub_w
        except Exception:
            sub_h = int(sub_w * 9 / 16)  # 默认 16:9

    pos_func = POSITION_MAP.get(position)
    if not pos_func:
        pos_func = POSITION_MAP["bottom-right"]
    pos_x, pos_y = pos_func(main_w, main_h, sub_w, sub_h, margin)

    # 主视频预处理：[0:v] -> [base]，用于 overlay 底层
    base_label = "0:v"
    pre_filters = []
    if target_duration is not None and main_dur is not None:
        if main_dur < target_duration - 0.05:
            extend_sec = target_duration - main_dur
            pre_filters.append(f"[0:v]tpad=stop_mode=clone:stop_duration={extend_sec}[base]")
            base_label = "base"
        elif main_dur > target_duration + 0.05:
            pre_filters.append(f"[0:v]trim=0:{target_duration},setpts=PTS-STARTPTS[base]")
            base_label = "base"

    # 子视频：crop -> scale
    if sub_crop:
        x1, y1, x2, y2 = sub_crop
        cw, ch = x2 - x1, y2 - y1
        sub_chain = f"[1:v]crop={cw}:{ch}:{x1}:{y1},scale={sub_w}:{sub_h}[sub]"
    else:
        sub_chain = f"[1:v]scale={sub_w}:{sub_h}[sub]"

    # 合并 filter：pre + sub + overlay
    if pre_filters:
        overlay_filter = f"{pre_filters[0]};{sub_chain};[{base_label}][sub]overlay={pos_x}:{pos_y}:format=auto[outv]"
    else:
        overlay_filter = f"{sub_chain};[0:v][sub]overlay={pos_x}:{pos_y}:format=auto[outv]"

    args = ["-i", main_path, "-i", sub_path, "-filter_complex", overlay_filter]
    if sub_audio:
        args += ["-map", "[outv]", "-map", "1:a:0"]
    else:
        args += ["-map", "[outv]"]

    if target_duration is not None:
        args += ["-t", str(target_duration)]

    args += ["-c:v", "libx264", "-preset", ffmpeg_preset, "-c:a", "aac", output_path]

    _run_ffmpeg(args, "overlay")
    logger.info("Step 4 (FFmpeg) 完成：%s", output_path)
    return output_path


def overlay_cartoon_fixed(
    digital_human_path: str,
    cartoon_path: str,
    output_path: str,
    cartoon_scale: float = 0.35,
    cartoon_y_ratio: float = 0.12,
    ffmpeg_preset: str = "ultrafast",
) -> str:
    """
    固定位置叠加卡通头到数字人视频（无 face detection，纯 FFmpeg，极快）。
    卡通头位置：水平居中，垂直位于画面上部 cartoon_y_ratio 处。
    用于数字人固定机位场景，可替代 replace_head 大幅加速 Step 3。
    """
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg 未安装或不在 PATH 中")
    check_video_path(digital_human_path)
    check_video_path(cartoon_path)
    ensure_output_dir(output_path)

    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", digital_human_path],
            capture_output=True, text=True, check=True,
        )
        parts = r.stdout.strip().split(",")
        main_w, main_h = int(parts[0]), int(parts[1])
    except Exception:
        main_w, main_h = 1920, 1080

    sub_w = int(main_w * cartoon_scale)
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", cartoon_path],
            capture_output=True, text=True, check=True,
        )
        sw, sh = int(r.stdout.strip().split(",")[0]), int(r.stdout.strip().split(",")[1])
        sub_h = int(sub_w * sh / sw) if sw else sub_w
    except Exception:
        sub_h = sub_w

    pos_x = (main_w - sub_w) // 2
    pos_y = int(main_h * cartoon_y_ratio)

    # overlay: [0:v]=数字人(主), [1:v]=卡通头(子)，子叠加到主上，保留主音轨
    filter_complex = (
        f"[1:v]scale={sub_w}:{sub_h}[cartoon];"
        f"[0:v][cartoon]overlay={pos_x}:{pos_y}:format=auto[outv]"
    )
    args = [
        "-i", digital_human_path, "-i", cartoon_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", ffmpeg_preset,
        "-c:a", "aac", "-shortest", output_path,
    ]
    _run_ffmpeg(args, "overlay_cartoon_fixed")
    logger.info("Step 3 (FFmpeg 固定叠加) 完成：%s", output_path)
    return output_path
