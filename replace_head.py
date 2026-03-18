"""
卡通头部覆盖数字人视频

用法：
    python replace_head.py

需要先安装依赖：
    pip install opencv-python moviepy numpy
"""

import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 导入头部替换模块
from video_module_sucess.core.head_replace import replace_head


def main():
    print("=" * 50)
    print("卡通头部覆盖数字人视频")
    print("=" * 50)

    # 默认路径
    default_pig = PROJECT_ROOT / "video_module_sucess" / "cartoon" / "pig.mp4"
    default_video = PROJECT_ROOT / "video_module_sucess" / "action_clips" / "jirian" / "final.mp4"
    default_output = PROJECT_ROOT / "output" / "head_replaced.mp4"

    # 1. 输入卡通头部视频路径
    pig_path = input(f"\n请输入卡通头部视频路径（直接回车使用默认值）:\n  默认: {default_pig}\n> ").strip()
    if not pig_path:
        pig_path = str(default_pig)

    if not os.path.exists(pig_path):
        print(f"[错误] 文件不存在: {pig_path}")
        return

    # 2. 输入数字人视频路径
    video_path = input(f"\n请输入数字人视频路径（直接回车使用默认值）:\n  默认: {default_video}\n> ").strip()
    if not video_path:
        video_path = str(default_video)

    if not os.path.exists(video_path):
        print(f"[错误] 文件不存在: {video_path}")
        return

    # 3. 输入输出路径
    output_path = input(f"\n请输入输出视频路径（直接回车使用默认值）:\n  默认: {default_output}\n> ").strip()
    if not output_path:
        output_path = str(default_output)

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 4. 额外参数（可选）
    print("\n可选参数（直接回车使用默认值）:")
    head_scale = input("  头部缩放倍数 (默认 1.8): ").strip()
    head_scale = float(head_scale) if head_scale else 1.8

    y_offset = input("  头部上移比例 (默认 0.25): ").strip()
    y_offset = float(y_offset) if y_offset else 0.25

    print("\n" + "=" * 50)
    print("开始处理...")
    print(f"  卡通头部: {pig_path}")
    print(f"  数字人视频: {video_path}")
    print(f"  输出路径: {output_path}")
    print("=" * 50 + "\n")

    try:
        replace_head(
            video_path=video_path,
            pig_path=pig_path,
            output_path=output_path,
            head_scale=head_scale,
            y_offset_ratio=y_offset,
            keep_audio=True,
        )
        print("\n" + "=" * 50)
        print(f"处理完成！输出文件: {output_path}")
        print("=" * 50)
    except Exception as e:
        print(f"\n[错误] 处理失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
