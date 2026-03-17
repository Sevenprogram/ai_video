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

# 目标群聊 chat_id（监听机器人需要在这个群里）
FEISHU_TARGET_CHAT_ID: str = "oc_10e5e1d2510be2545d0b9c703b8b9e9d"

# OpenClaw 机器人在飞书的 open_id（用于 @ 它，格式 ou_xxx；不需要 @ 则留空）
OPENCLAW_BOT_OPEN_ID: str = "ou_66850eb2f6f36794adb49dc81af0031a"

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
PROXY_API_KEY: str = "sk-q9oguhgaOxnNukTVpGT7REKFB3JaT2CFkUHQ6fW7kjkVlj9e"               # 填入中转站的 API Key
PROXY_BASE_URL: str = "https://jeniya.top/v1"
PROXY_MODEL: str = "gemini-2.0-flash" # 可换为 claude-3-5-sonnet-20241022 等

# ===== 视频时长 =====
VIDEO_DURATION_MINUTES: int = 3   # 目标文稿/视频时长（分钟），会注入到文稿和分镜提示词中

# ===== HeyGen 数字人视频 =====
HEYGEN_API_KEY: str = "sk_V2_hgu_kPJmzdKZSV0_iXlpj2jQT1Q0hONv3lBh3hMIrGyUKprC"
HEYGEN_AVATAR_ID: str = "a761ce70b43447ab8383684d98afcf22"
HEYGEN_VOICE_ID: str = "16b83de110ba45ec9537eaf28be7e448"
