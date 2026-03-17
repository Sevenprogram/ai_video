"""
数字人动作集生成（HeyGen）

思路：
- 先离线生成一批“基础常态动作 + 常见特殊动作”的数字人视频片段，
  例如：站立+轻微手势、点头、摊手、看向侧屏、操作鼠标等。
- 后续具体视频只需要按分镜拼接这些已有片段，而不是每次都重新让 HeyGen
  生成一整套独一无二的动作。

使用前准备：
- pip install requests
- 在 config.py 中填好 HEYGEN_API_KEY、HEYGEN_AVATAR_ID、HEYGEN_VOICE_ID
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Iterable

import requests

# 兼容两种运行方式：
# 1) python -m video_module.actions_library   （推荐）
# 2) python video_module/actions_library.py   （直接运行）
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import HEYGEN_API_KEY, HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID


HEYGEN_BASE_URL = "https://api.heygen.com/v2"


@dataclass
class ActionPreset:
    """单个动作预设."""

    key: str
    description: str
    motion_prompt: str
    default_duration_sec: float = 6.0


# 基础常态动作 + 一些常见补动作
BASE_ACTION_PRESETS: Dict[str, ActionPreset] = {
    # 常态：双手平摊、偶尔微动，适合作为多数口播段落的底座
    "idle_hands_open": ActionPreset(
        key="idle_hands_open",
        description="常态：双手自然平摊在身体前方，始终有轻微手部动作",
        motion_prompt=(
            "The avatar faces the camera with both hands clearly visible in front of the body "
            "at a comfortable height. Throughout the whole clip, the hands must NOT stay still: "
            "they continuously make small, natural gestures such as opening and closing slightly, "
            "subtle pointing, counting on fingers, or light chopping motions to emphasize points. "
            "Movements are continuous but not exaggerated, always staying within frame and matching "
            "a calm, confident speaking style."
        ),
        default_duration_sec=10.0,
    ),
    # 轻微点头，常用应答/认可
    "nod_light": ActionPreset(
        key="nod_light",
        description="轻微点头 1-2 次，表示认可或同意",
        motion_prompt=(
            "The avatar gently nods one or two times to show agreement, while keeping "
            "a relaxed posture and natural eye contact with the camera."
        ),
        default_duration_sec=4.0,
    ),
    # 看向侧屏，适合配合“看盘/看图表”画面
    "look_side_screen": ActionPreset(
        key="look_side_screen",
        description="视线从镜头转向右侧屏幕，短暂停留再回到镜头",
        motion_prompt=(
            "The avatar shifts gaze from the camera to a screen on the right side, "
            "pauses for a moment as if reading data, then smoothly looks back at the camera."
        ),
        default_duration_sec=6.0,
    ),
    # 摊手，无奈/反问
    "shrug_open_hands": ActionPreset(
        key="shrug_open_hands",
        description="双手微摊，肩膀轻微上抬，表达无奈或质疑",
        motion_prompt=(
            "The avatar slightly raises both shoulders and opens palms upward in a small shrug, "
            "showing a 'what can you do?' attitude, then returns to a neutral pose."
        ),
        default_duration_sec=5.0,
    ),
}


class HeyGenClient:
    """简单的 HeyGen 封装，只用于生成单段头像视频."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or HEYGEN_API_KEY
        if not self.api_key:
            raise ValueError("请在 config.py 或环境变量 HEYGEN_API_KEY 中配置 HeyGen API Key")

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def generate_avatar_video(
        self,
        script: str,
        avatar_id: str | None = None,
        voice_id: str | None = None,
        width: int = 1920,
        height: int = 1080,
        title: str = "action_clip",
    ) -> str:
        """
        调用 HeyGen 生成单个头像视频，返回 video_id。

        这里使用官方 v2 生成接口（文本转语音 + Avatar）：
        POST https://api.heygen.com/v2/video/generate
        文档参考：Generate Studio Video / Create Avatar Video V2
        """
        avatar_id = avatar_id or HEYGEN_AVATAR_ID
        voice_id = voice_id or HEYGEN_VOICE_ID
        if not avatar_id or not voice_id:
            raise ValueError("请在 config.py 中配置 HEYGEN_AVATAR_ID 和 HEYGEN_VOICE_ID")

        url = f"{HEYGEN_BASE_URL}/video/generate"
        payload = {
            "title": title,
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "scale": 1,
                    },
                    "voice": {
                        "type": "text",
                        "voice_id": voice_id,
                        "input_text": script,
                    },
                }
            ],
            "dimension": {"width": width, "height": height},
            "caption": False,
        }
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        video_id = data.get("data", {}).get("video_id") or data.get("video_id")
        if not video_id:
            raise RuntimeError(f"HeyGen 创建视频失败，返回内容：{data}")
        return video_id

    def get_video_info(self, video_id: str) -> dict:
        """查询视频状态与下载地址。

        对应 HeyGen 文档中的 Get Video Status/Details 接口：
        GET /v1/video_status.get?video_id=...
        """
        url = "https://api.heygen.com/v1/video_status.get"
        params = {"video_id": video_id}
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def wait_for_video(
        self,
        video_id: str,
        poll_interval: float = 5.0,
        timeout: float = 600.0,
    ) -> str:
        """
        轮询等待视频生成完成，返回可下载的 mp4 地址。
        """
        import time

        start = time.time()
        while True:
            info = self.get_video_info(video_id)
            data = info.get("data", {}) if isinstance(info, dict) else {}
            # 文档中 status 一般位于 data.status
            status = data.get("status") or info.get("status")
            if status in {"completed", "succeeded"}:
                # 优先使用正式视频地址，其次 gif
                url = (
                    data.get("video_url")
                    or data.get("url")
                    or info.get("video_url")
                    or info.get("url")
                    or data.get("gif_url")
                )
                if not url:
                    raise RuntimeError(f"视频已完成，但未找到下载地址：{info}")
                return url
            if status in {"failed", "error"}:
                raise RuntimeError(f"视频生成失败：{info}")
            if time.time() - start > timeout:
                raise TimeoutError(f"等待 HeyGen 视频超时（{timeout}s），当前状态：{status}")
            time.sleep(poll_interval)

    @staticmethod
    def download_video_file(url: str, save_path: str) -> None:
        """下载 mp4 文件到本地。"""
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)


def generate_base_action_library(
    output_dir: str,
    script_template: str = (
        "So, this is a reusable motion clip for our trading videos. [pause] "
        "I stay relaxed, keep both hands clearly visible, and make small, natural gestures "
        "as if I am explaining a chart or walking through a setup. [pause] "
        "Nothing too dramatic, but the hands should keep moving a little, so the avatar never "
        "looks frozen on screen."
    ),
    presets: Dict[str, ActionPreset] | None = None,
    only_keys: Iterable[str] | None = None,
) -> List[str]:
    """
    批量生成基础动作视频片段。

    :param output_dir: 输出目录，例如 "video_module/action_clips"
    :param script_template: 每个动作使用的台词模版，可根据需要自定义
    :param presets: 若不提供则使用 BASE_ACTION_PRESETS
    :return: 已生成的本地文件路径列表
    """
    presets = presets or BASE_ACTION_PRESETS

    # 若指定 only_keys，则只生成这些 key 对应的动作
    if only_keys is not None:
        only_keys = list(only_keys)
        presets = {k: v for k, v in presets.items() if k in only_keys}
        missing = [k for k in only_keys if k not in presets]
        if missing:
            print(f"警告：以下动作 key 未在预设中找到，将被忽略：{', '.join(missing)}")
    client = HeyGenClient()
    os.makedirs(output_dir, exist_ok=True)

    saved_paths: List[str] = []
    for key, preset in presets.items():
        print(f"[INFO] 准备生成动作 '{key}': {preset.description}")
        # 这里可以按需要把动作描述加进脚本中，方便后续人工识别片段
        script = f"{script_template}"
        title = f"action_{key}"
        print(f"[INFO] 调用 HeyGen 创建视频任务: title={title}")
        video_id = client.generate_avatar_video(script=script, title=title)
        print(f"[INFO] 创建成功，video_id={video_id}，开始轮询状态...")
        url = client.wait_for_video(video_id)
        save_path = os.path.join(output_dir, f"{key}.mp4")
        print(f"[INFO] 视频已生成，下载地址: {url}")
        print(f"[INFO] 开始下载到本地文件: {save_path}")
        client.download_video_file(url, save_path)
        saved_paths.append(save_path)
        print(f"[OK] 动作 '{key}' 已保存: {save_path}")

    return saved_paths


if __name__ == "__main__":
    """
    直接运行本文件的交互用法：

    1. 终端执行：
       python -m video_module.actions_library

    2. 程序会列出当前支持的动作 key，例如：
       - idle_hands_open
       - nod_light
       - look_side_screen
       - shrug_open_hands

    3. 在提示中输入想生成的动作 key，多项用英文逗号分隔：
       例如：idle_hands_open,nod_light

    若直接回车，不输入任何内容，则会生成所有预设动作。
    """
    import argparse

    parser = argparse.ArgumentParser(description="生成 HeyGen 数字人基础动作视频片段")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "action_clips"),
        help="输出目录，默认 video_module/action_clips",
    )
    parser.add_argument(
        "--actions",
        type=str,
        nargs="*",
        help=(
            "只生成指定动作 key，对应 BASE_ACTION_PRESETS 的 key。"
            "例如：--actions idle_hands_open nod_light"
        ),
    )
    args = parser.parse_args()

    # 如果没有通过命令行指定 --actions，则在程序内交互选择
    actions = args.actions
    # actions = ["idle_hands_open"]
    if actions is None:
        print("当前可用动作 key：")
        for k, preset in BASE_ACTION_PRESETS.items():
            print(f"- {k}: {preset.description}")
        line = input("请输入要生成的动作 key（多项用英文逗号分隔，直接回车表示全部）：").strip()
        if line:
            actions = [s.strip() for s in line.split(",") if s.strip()]
        else:
            actions = None  # 表示全部

    generate_base_action_library(
        output_dir=args.output_dir,
        only_keys=actions,
    )

