#!/usr/bin/env python3
"""
速度测试脚本：测试 180 秒视频的生成速度
"""
import os
import sys
import time
import logging
import subprocess

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 添加项目路径
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# 测试配置
RECORDING_PATH = os.path.join(ROOT, "video_module/video_shoot/recording.mp4")
DIGITAL_HUMAN_DIR = os.path.join(ROOT, "video_module/action_clips/jirian")
PIG_PATH = os.path.join(ROOT, "video_module/action_clips/pig.mp4")
OUTPUT_DIR = os.path.join(ROOT, "outputs_speed_test")
VIDEO_MODULE_DIR = os.path.join(ROOT, "video_module")
TARGET_DURATION = 180.0  # 180 秒


def create_test_audio(output_path, duration_sec=180):
    """使用 ffmpeg 创建一个简单音调测试音频"""
    try:
        # 使用 ffmpeg 生成一个简单音调，然后转换为 mp3
        # 先生成 wav
        wav_path = output_path.replace(".mp3", ".wav")
        result = subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_sec}",
            "-ar", "16000", "-ac", "1", wav_path
        ], capture_output=True, text=True)
        
        if result.returncode != 0 or not os.path.exists(wav_path):
            logger.warning("创建测试音频失败: %s", result.stderr)
            return None
        
        # 转换为 mp3
        result = subprocess.run([
            "ffmpeg", "-y", "-i", wav_path,
            "-acodec", "libmp3lame", "-q:a", "2", output_path
        ], capture_output=True, text=True)
        
        # 清理 wav
        if os.path.exists(wav_path):
            os.remove(wav_path)
        
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            logger.warning("转换 mp3 失败: %s", result.stderr)
            return None
    except Exception as e:
        logger.warning("创建测试音频失败: %s", e)
        return None


def main():
    # 确认测试文件存在
    if not os.path.exists(RECORDING_PATH):
        logger.error("测试视频不存在: %s", RECORDING_PATH)
        return
    
    if not os.path.exists(PIG_PATH):
        logger.error("猪头视频不存在: %s", PIG_PATH)
        return
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 获取数字人视频
    clip_paths = []
    for f in sorted(os.listdir(DIGITAL_HUMAN_DIR)):
        if f.endswith((".mp4", ".webm", ".mov")):
            clip_paths.append(os.path.join(DIGITAL_HUMAN_DIR, f))
    
    if not clip_paths:
        logger.error("未找到数字人视频")
        return
    
    # 创建测试音频
    test_audio = os.path.join(OUTPUT_DIR, "test_audio.mp3")
    test_audio = create_test_audio(test_audio, TARGET_DURATION)
    if not test_audio:
        logger.error("无法创建测试音频")
        return
    
    logger.info("=" * 50)
    logger.info("速度测试开始")
    logger.info("=" * 50)
    logger.info("测试视频: %s", RECORDING_PATH)
    logger.info("目标时长: %.0f 秒", TARGET_DURATION)
    logger.info("数字人视频: %d 个", len(clip_paths))
    logger.info("测试音频: %s", test_audio)
    logger.info("输出目录: %s", OUTPUT_DIR)
    logger.info("=" * 50)
    
    # 切换到 video_module 目录以确保模块导入正确
    os.chdir(VIDEO_MODULE_DIR)
    sys.path.insert(0, VIDEO_MODULE_DIR)
    
    # 测试 pipeline
    from pipeline import build_video
    
    output_path = os.path.join(OUTPUT_DIR, "test_output.mp4")
    work_dir = os.path.join(OUTPUT_DIR, "work")
    
    start_time = time.time()
    
    try:
        result = build_video(
            clip_paths=clip_paths,
            audio_path=test_audio,
            pig_path=PIG_PATH,
            main_path=RECORDING_PATH,
            output_path=output_path,
            target_duration=TARGET_DURATION,
            audio_as_canonical=True,  # 以音频为时长基准
            work_dir=work_dir,
            skip_existing=False,
            ffmpeg_preset="ultrafast",
            detect_interval=30,
        )
        elapsed = time.time() - start_time
        
        logger.info("=" * 50)
        logger.info("测试完成!")
        logger.info("输出: %s", result)
        logger.info("耗时: %.1f 秒 (%.1f 分钟)", elapsed, elapsed / 60)
        logger.info("视频时长: %.0f 秒", TARGET_DURATION)
        logger.info("处理速度: %.1f x realtime", TARGET_DURATION / elapsed if elapsed > 0 else 0)
        logger.info("=" * 50)
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("测试失败: %s", e)
        logger.error("耗时: %.1f 秒 (%.1f 分钟)", elapsed, elapsed / 60)
        if elapsed > 0:
            logger.error("预估处理速度: %.1f x realtime", TARGET_DURATION / elapsed)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
