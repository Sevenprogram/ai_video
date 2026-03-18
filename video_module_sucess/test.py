"""
测试脚本：直接调用 main.py 中的函数，用已有的测试文件验证完整流程。

测试步骤：
  1. 读取已有 script.txt
  2. 调用 build_storyboard_prompt()  → 生成分镜提示词
  3. 调用 gemini_complete()          → 让 Gemini 生成分镜 JSON
  4. 解析 JSON（验证格式是否正确）
  5. 调用 build_recording_instruction() → 生成录屏指令文本
  6. 调用 send_as_user_and_wait_reply()  → 发给 OpenClaw

运行方式：
    python video_module/test.py
"""

import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 直接引用 main.py 中的函数
from main import build_storyboard_prompt, build_recording_instruction
from module import gemini_complete
from openclaw import send_as_user_and_wait_reply

TEST_DIR        = os.path.join(ROOT, "outputs", "视频_20260316_1739")
SCRIPT_PATH     = os.path.join(TEST_DIR, "script.txt")
STORYBOARD_PATH = os.path.join(TEST_DIR, "storyboard.txt")
STORYBOARD_XLSX = os.path.join(TEST_DIR, "storyboard.xlsx")
RECORDING_PATH  = os.path.join(TEST_DIR, "recording_task.txt")
FOLDER_NAME     = "视频_20260316_1739"


def log(msg):
    print(f"[TEST] {msg}")


if __name__ == "__main__":
    print("=" * 60)
    print("  测试 main.py 函数：分镜生成 → 录屏指令 → 发送 OpenClaw")
    print("=" * 60)

    # ── Step 1：读取文稿 ───────────────────────────────────────────────────
    log("Step 1 - 读取 script.txt...")
    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        script = f.read()
    log(f"  文稿长度：{len(script)} 字符")

    # ── Step 2：调用 build_storyboard_prompt() ────────────────────────────
    log("Step 2 - 调用 build_storyboard_prompt()...")
    prompt = build_storyboard_prompt(script)
    log(f"  提示词长度：{len(prompt)} 字符，前 100 字：{prompt[:100]!r}")

    # ── Step 3：调用 gemini_complete() 生成分镜 JSON ──────────────────────
    if os.path.exists(STORYBOARD_PATH):
        ans = input("\n发现已有 storyboard.txt，复用？(y=复用 / n=重新生成): ").strip().lower()
        if ans != "n":
            log("Step 3 - 复用已有 storyboard.txt。")
            with open(STORYBOARD_PATH, "r", encoding="utf-8") as f:
                storyboard = f.read()
        else:
            log("Step 3 - 调用 gemini_complete() 生成分镜...")
            storyboard = gemini_complete(prompt)
            with open(STORYBOARD_PATH, "w", encoding="utf-8") as f:
                f.write(storyboard)
            log(f"  分镜已保存：{STORYBOARD_PATH}")
    else:
        log("Step 3 - 调用 gemini_complete() 生成分镜...")
        storyboard = gemini_complete(prompt)
        with open(STORYBOARD_PATH, "w", encoding="utf-8") as f:
            f.write(storyboard)
        log(f"  分镜已保存：{STORYBOARD_PATH}")

    # ── Step 4：解析 JSON，验证格式 ───────────────────────────────────────
    log("Step 4 - 解析分镜 JSON...")
    # 清理可能的 markdown 代码块
    text = storyboard.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]

    try:
        data = json.loads(text)
        shots = data["shots"] if isinstance(data, dict) and "shots" in data else data
        log(f"  解析成功，共 {len(shots)} 个镜头，总时长约 {shots[-1].get('end_sec', 0):.1f} 秒。")
        for s in shots:
            print(f"    #{s.get('id'):>2} | {s.get('start_sec'):>6.1f}s-{s.get('end_sec'):>6.1f}s"
                  f" | {s.get('source', ''):10} | {str(s.get('url', ''))[:45]}")
    except Exception as e:
        log(f"  ❌ JSON 解析失败：{e}")
        log(f"  原始内容前 300 字：\n{storyboard[:300]}")
        shots = []

    # ── Step 5：调用 build_recording_instruction() ────────────────────────
    if shots:
        log("\nStep 5 - 调用 build_recording_instruction()...")
        instruction = build_recording_instruction(shots, FOLDER_NAME)
        with open(RECORDING_PATH, "w", encoding="utf-8") as f:
            f.write(instruction)
        log(f"  录屏指令已保存：{RECORDING_PATH}")
        print("\n── 指令预览（前 600 字）──")
        try:
            print(instruction[:600])
        except UnicodeEncodeError:
            sys.stdout.buffer.write((instruction[:600] + "\n").encode("utf-8", errors="replace"))
        print("─" * 40)
    else:
        instruction = ""
        log("Step 5 - 跳过（分镜解析失败）。")

    # ── Step 6：调用 send_as_user_and_wait_reply() 发给 OpenClaw ──────────
    if instruction:
        ans = input("\nStep 6 - 是否发送录屏任务给 OpenClaw？(y=发送 / n=跳过): ").strip().lower()
        if ans != "n":
            log("  通过飞书发送中（首次运行会打开浏览器授权）...")
            reply = send_as_user_and_wait_reply(instruction, timeout=600)
            if reply:
                log(f"  OpenClaw 回复：{reply}")
            else:
                log("  未收到回复（超时），请手动确认录制状态。")
        else:
            log("Step 6 - 已跳过。")

    # ── 汇总 ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试完成，生成文件：")
    for label, path in [
        ("故事板 txt ", STORYBOARD_PATH),
        ("故事板 xlsx", STORYBOARD_XLSX),
        ("录屏指令   ", RECORDING_PATH),
    ]:
        status = "✓" if os.path.exists(path) else "✗ 未生成"
        print(f"  [{status}] {label}: {os.path.basename(path)}")
    print("=" * 60)
