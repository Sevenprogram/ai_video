"""
测试视频合成 - 使用用户指定的文件
"""
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# 使用用户指定的文件
PIG_PATH = "video_module/cartoon/pig.mp4"
DIGITAL_HUMAN_VIDEO = "video_module/action_clips/jirian/final.mp4"
RECORDING_PATH = "outputs/录屏_20260318_1149/recording.mp4"
AUDIO_PATH = "video_module/test/audio.mp3"

# 输出目录
OUTPUT_DIR = "video_module/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_ffmpeg(cmd, desc=""):
    """执行 FFmpeg 命令"""
    print(f"{desc}...")
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result


def main():
    # 检查文件
    print("检查输入文件...")
    for name, path in [("猪头", PIG_PATH), ("数字人", DIGITAL_HUMAN_VIDEO), ("录屏", RECORDING_PATH), ("音频", AUDIO_PATH)]:
        if os.path.exists(path):
            print(f"  ✓ {name}: {path}")
        else:
            print(f"  ✗ {name}: {path} (不存在)")
            return
    
    output_path = os.path.join(OUTPUT_DIR, "test_output.mp4")
    
    print("\n开始合成视频...")
    print(f"  数字人视频: {DIGITAL_HUMAN_VIDEO}")
    print(f"  音频: {AUDIO_PATH}")
    print(f"  猪头: {PIG_PATH}")
    print(f"  录屏背景: {RECORDING_PATH}")
    print(f"  输出: {output_path}")
    
    # Step 1: 裁剪数字人视频到目标时长
    print("\n=== Step 1: 裁剪数字人视频 ===")
    step1_path = os.path.join(OUTPUT_DIR, "test_step1.mp4")
    
    # 获取音频时长
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", AUDIO_PATH],
        capture_output=True, text=True, check=True
    )
    audio_duration = float(result.stdout.strip())
    print(f"音频时长: {audio_duration:.2f}秒")
    
    # 裁剪视频
    cmd = [
        "ffmpeg", "-y", "-i", DIGITAL_HUMAN_VIDEO,
        "-t", str(audio_duration),
        "-c", "copy", step1_path
    ]
    run_ffmpeg(cmd, "裁剪视频")
    print(f"Step 1 完成: {step1_path}")
    
    # Step 2: 替换音频
    print("\n=== Step 2: 替换音频 ===")
    step2_path = os.path.join(OUTPUT_DIR, "test_step2_audio.mp4")
    
    cmd = [
        "ffmpeg", "-y", "-i", step1_path, "-i", AUDIO_PATH,
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        step2_path
    ]
    run_ffmpeg(cmd, "替换音频")
    print(f"Step 2 完成: {step2_path}")
    
    # Step 3: 猪头替换
    print("\n=== Step 3: 猪头替换 ===")
    step3_path = os.path.join(OUTPUT_DIR, "test_step3_pig.mp4")
    
    sys.path.insert(0, os.path.join(BASE_DIR, "video_module"))
    from video_module_sucess.core.head_replace import replace_head as replace_head_success
    
    replace_head_success(
        video_path=step2_path,
        pig_path=PIG_PATH,
        output_path=step3_path,
        head_scale=1.8,
        y_offset_ratio=0.25,
        keep_audio=True,
    )
    print(f"Step 3 完成: {step3_path}")
    
    # Step 4: 画中画
    print("\n=== Step 4: 画中画 ===")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", RECORDING_PATH,
        "-i", step3_path,
        "-filter_complex", "[1:v]scale=346:-1[sub];[0:v][sub]overlay=main_w-overlay_w-20:main_h-overlay_h-20",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        output_path
    ]
    run_ffmpeg(cmd, "画中画合成")
    print(f"Step 4 完成: {output_path}")
    
    print(f"\n{'='*50}")
    print(f"完成! 输出: {output_path}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
