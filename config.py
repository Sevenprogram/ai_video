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

# 目标群聊 chat_id（群聊模式下监听机器人需在此群）
FEISHU_TARGET_CHAT_ID: str = "oc_10e5e1d2510be2545d0b9c703b8b9e9d"

# 指定机器人的 open_id（格式 ou_xxx），用于：
#   - 群聊中 @ 该机器人
#   - 私聊（P2P）该机器人：python3 test_feishu_send.py --p2p
# 获取方式：python3 get_bot_open_id.py 列出群成员；或飞书开放平台 API 调试台搜索复制
# 注意：若目标机器人与当前应用非同一应用，会出现 open_id cross app 错误，改用 --p2p-chat-id
OPENCLAW_BOT_OPEN_ID: str = "ou_66850eb2f6f36794adb49dc81af0031a"

# 目标机器人的 app_id（格式 cli_xxx），用于创建 P2P 会话以绕过 open_id cross app。
# 获取方式：飞书开放平台 → 目标应用 → 凭证与基础信息；若与 FEISHU_APP_ID 相同可留空
OPENCLAW_BOT_APP_ID: str = "cli_a93aa1717ff8dbc6"

# 与 OpenClaw 的 P2P 会话 chat_id（格式 oc_xxx）。配置后所有消息将直接发到此机器人的私聊，不再使用群组。
# 获取方式：python3 get_p2p_chat_id.py（需先配置 OPENCLAW_BOT_APP_ID，并完成一次 OAuth）
# 若未配置，程序会尝试自动创建并缓存
OPENCLAW_P2P_CHAT_ID: str = ""

# True = 优先发到机器人私聊（OPENCLAW_P2P_CHAT_ID）；False = 发到群聊
OPENCLAW_USE_P2P: bool = True

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
PROXY_API_KEY: str = "sk-q9oguhgaOxnNukTVpGT7REKFB3JaT2CFkUHQ6fW7kjkVlj9e"
PROXY_BASE_URL: str = "https://jeniya.top/v1"
PROXY_MODEL: str = "gemini-2.0-flash"

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
VIDEO_DIGITAL_HUMAN_DEFAULT: str = "idle_hands_open.mp4"   # 数字人默认
VIDEO_CARTOON_HEAD_DEFAULT: str = "pig.mp4"                # 卡通头部默认
VIDEO_SHOOT_DEFAULT: str = "template.mp4"                  # 录屏默认（video_shoot 中常用名）
