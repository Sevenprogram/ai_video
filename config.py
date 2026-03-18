# ============================================================
# 全局配置文件 —— 所有 API Key、ID、默认参数均在此处直接填写
# ============================================================

# ===== OpenClaw Gateway =====
OPENCLAW_GATEWAY_URL: str = ""        # 例：http://45.144.136.146:18789
OPENCLAW_GATEWAY_TOKEN: str = "a493acdf60f8967921bfc8120d42425b212fb1c45eb40b1c"

# ===== 飞书 =====
FEISHU_BASE_URL: str = "https://open.feishu.cn"
FEISHU_APP_ID: str = "cli_a93d7c3f39b8dbcc"
FEISHU_APP_SECRET: str = "HgEKF5zy1duNjybrDP92DfnXJphUjEOD"

# 目标群聊 chat_id，通过该群组向 OpenClaw 发送消息并接收回复
FEISHU_TARGET_CHAT_ID: str = "oc_10e5e1d2510be2545d0b9c703b8b9e9d"
# 与 OpenClaw 机器人的私聊 chat_id（可选）。若填写则可通过「机器人聊天框」直接发指令，无需群组
# 获取方式：运行 python test_send_to_bot_dm.py --listen-chat-id，在飞书里给 openclaw 机器人发一条消息即可
# 注意：私聊需要用户在飞书应用可用范围内，否则会报 open_id cross app 错误
FEISHU_BOT_CHAT_ID: str = ""
# 飞书事件订阅：在开发者后台配置请求地址后，填入 Verification Token 和 Encrypt Key（未加密可留空）
FEISHU_VERIFICATION_TOKEN: str = ""
FEISHU_ENCRYPT_KEY: str = ""

# 测试指令（python openclaw.py 直接运行时使用）
TEST_TASK_TEXT: str = "ping: 请回复我一句 ok，并说明你当前可用的模型提供方列表。"

# ===== ElevenLabs TTS =====
ELEVENLABS_API_KEY: str = "sk_aad07cfc5ea980227eacbf73db7f5982275b7b52ea3abed8"
DEFAULT_VOICE_ID: str = "Cz0K1kOv9tD8l0b5Qu53"
DEFAULT_MODEL_ID: str = "eleven_v3"
DEFAULT_OUTPUT_FORMAT: str = "mp3_44100_128"

# ===== 大模型提供商切换 =====
# 可选值：
#   "gemini"  → 直连 Google Gemini API（需能访问 googleapis.com）
#   "jeniya"  → 通过 jeniya.top AI 中转站（兼容 OpenAI 格式），适合服务器环境
#   "claude"  → 直连 Anthropic Claude API
LLM_PROVIDER: str = "jeniya"

# ===== Claude（Anthropic）=====
ANTHROPIC_API_KEY: str = ""           # LLM_PROVIDER="claude" 时使用
CLAUDE_MODEL: str = "claude-3-5-sonnet-20241022"
CLAUDE_MAX_TOKENS: int = 2048

# ===== Gemini =====
GEMINI_API_KEY: str = "AIzaSyBVCDu0q3X4TA1sjsR1qu_vqdg0cWBm1Vg"
GEMINI_MODEL: str = "gemini-2.0-flash"
GEMINI_MAX_TOKENS: int = 4096

# ===== Jeniya AI 中转站（LLM_PROVIDER="jeniya" 时使用）=====
# 中转站地址：https://jeniya.top  注册后获取 API Key
# 使用 Jeniya 提供的 Gemini 2.0 Flash，不使用 OpenAI 模型
PROXY_API_KEY: str = "sk-q9oguhgaOxnNukTVpGT7REKFB3JaT2CFkUHQ6fW7kjkVlj9e"
PROXY_BASE_URL: str = "https://jeniya.top/v1"
PROXY_MODEL: str = "gemini-2.0-flash"   # Jeniya 中的 Gemini 2.0 Flash 模型

# ===== 视频时长 =====
VIDEO_DURATION_MINUTES: int = 3    # 目标文稿/视频时长（分钟），会注入到文稿和分镜提示词中
SHOT_MIN_DURATION_SEC: int = 40   # 每个分镜最少停留秒数（录屏时每个页面停留 40 秒 - 2 分钟）
SHOT_MAX_DURATION_SEC: int = 120  # 每个分镜最多停留秒数
OPENCLAW_REPLY_TIMEOUT: int = 1500  # 等待 OpenClaw 回复的最长秒数

# ===== HeyGen 数字人视频 =====
HEYGEN_API_KEY: str = "sk_V2_hgu_kPJmzdKZSV0_iXlpj2jQT1Q0hONv3lBh3hMIrGyUKprC"
HEYGEN_AVATAR_ID: str = "a761ce70b43447ab8383684d98afcf22"
HEYGEN_VOICE_ID: str = "16b83de110ba45ec9537eaf28be7e448"

# ===== 本地视频目录与默认文件（用于选择数字人、卡通头部、录屏视频）=====
# 目录相对于项目根目录，或绝对路径
VIDEO_SHOOT_DIR: str = "video_module/video_shoot"       # 录屏视频保存目录
VIDEO_DIGITAL_HUMAN_DIR: str = "/root/project/ai_video/video_module/action_clips"  # 数字人/口播视频目录
VIDEO_CARTOON_HEAD_DIR: str = "video_module/action_clips"  # 卡通头部视频目录
# 默认文件名（用户未填写时使用，相对于上述目录）
VIDEO_DIGITAL_HUMAN_DEFAULT: str = "jirian"   # 数字人默认（子文件夹名，合成该文件夹内所有视频片段）
VIDEO_CARTOON_HEAD_DEFAULT: str = "pig.mp4"                # 卡通头部默认
VIDEO_SHOOT_DEFAULT: str = "template.mp4"                  # 录屏默认（video_shoot 中常用名）

# ===== 卡通头部参数 =====
CARTOON_HEAD_SCALE: float = 3   # 卡通头相对人脸 bbox 的缩放倍数，默认 1.8
CARTOON_HEAD_WHITE_THRESH: int = 240  # 白色背景阈值（0-255），用于去除卡通头白色背景
