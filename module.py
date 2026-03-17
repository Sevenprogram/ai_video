"""
ElevenLabs 文字转语音 + Claude / Gemini 文本创作 API 封装
- TTS: 支持返回音频 bytes，或直接保存到本地文件
- Claude / Gemini: 提供提示词，调用 API 返回创作文本
使用前: pip install elevenlabs python-dotenv anthropic google-genai
配置: 参见 config.py（API Key、默认模型等）
"""
from elevenlabs.client import ElevenLabs

from config import (
    ELEVENLABS_API_KEY,
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_VOICE_ID,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_MAX_TOKENS,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MAX_TOKENS,
    LLM_PROVIDER,
    PROXY_API_KEY,
    PROXY_BASE_URL,
    PROXY_MODEL,
)

_client: ElevenLabs | None = None


def _get_client() -> ElevenLabs:
    global _client
    if _client is None:
        if not ELEVENLABS_API_KEY:
            raise ValueError("请在 .env 或系统环境中设置 ELEVENLABS_API_KEY")
        import httpx
        # trust_env=False：禁止 httpx 读取系统/环境代理，确保直连 ElevenLabs
        _client = ElevenLabs(
            api_key=ELEVENLABS_API_KEY,
            httpx_client=httpx.Client(trust_env=False),
        )
    return _client


def text_to_speech(
    text: str,
    voice_id: str = DEFAULT_VOICE_ID,
    model_id: str = DEFAULT_MODEL_ID,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    save_path: str | None = None,
) -> bytes:
    """
    将文字转为语音。

    :param text: 要转换的文本
    :param voice_id: 声音 ID，默认英文男声
    :param model_id: 模型 ID，默认多语言 v2
    :param output_format: 输出格式，默认 mp3_44100_128
    :param save_path: 若提供则同时保存到本地该路径
    :return: 音频二进制数据 (bytes)
    """
    client = _get_client()
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
    )
    data = b"".join(audio)
    if save_path:
        with open(save_path, "wb") as f:
            f.write(data)
    return data


def text_to_speech_to_file(text: str, path: str, **kwargs) -> str:
    """
    将文字转为语音并保存到本地文件。
    :param text: 要转换的文本
    :param path: 本地保存路径，如 "output.mp3"
    :return: 保存的文件路径
    """
    kwargs.pop("save_path", None)
    text_to_speech(text, save_path=path, **kwargs)
    return path


def play_audio(text: str, **kwargs) -> None:
    """转换并直接播放语音。需要系统安装 MPV 或 ffmpeg。"""
    from elevenlabs.play import play
    import io
    data = text_to_speech(text, **kwargs)
    play(io.BytesIO(data))


# ---------- Claude 创作 ----------

_claude_client = None


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        if not ANTHROPIC_API_KEY:
            raise ValueError("请在 config 或环境变量中设置 ANTHROPIC_API_KEY")
        from anthropic import Anthropic
        _claude_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _claude_client


def claude_complete(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    使用 Claude API 根据提示词进行创作，返回生成的文本。

    :param prompt: 用户提示词（你要让 Claude 写什么）
    :param system_prompt: 可选系统提示，设定角色或风格
    :param model: 模型 ID，默认使用 config.CLAUDE_MODEL
    :param max_tokens: 最大生成长度，默认使用 config.CLAUDE_MAX_TOKENS
    :return: Claude 生成的文本
    """
    client = _get_claude_client()
    kwargs = {
        "model": model or CLAUDE_MODEL,
        "max_tokens": max_tokens or CLAUDE_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt
    msg = client.messages.create(**kwargs)
    return msg.content[0].text


# ---------- 文稿 → 音频 一键流程 ----------


def script_to_audio(
    prompt: str,
    system_prompt: str = "",
    save_path: str = "output.mp3",
    save_script_path: str | None = None,
    **tts_kwargs,
) -> tuple[str, str]:
    """
    用 Claude 根据提示词生成文稿，再用 ElevenLabs 转为音频并保存。

    :param prompt: 创作提示词（例如「写一段 1 分钟的早安播报」）
    :param system_prompt: 可选，设定 Claude 的角色或风格
    :param save_path: 音频保存路径，默认 output.mp3
    :param save_script_path: 若提供，将生成的文稿保存到该文本文件
    :param tts_kwargs: 传给 text_to_speech 的额外参数（如 voice_id、model_id）
    :return: (生成的文稿文本, 音频文件路径)
    """
    script = claude_complete(prompt, system_prompt=system_prompt)
    text_to_speech_to_file(script, save_path, **tts_kwargs)
    if save_script_path:
        with open(save_script_path, "w", encoding="utf-8") as f:
            f.write(script)
    return script, save_path


# ---------- Jeniya AI 中转站（OpenAI 兼容格式）----------


def _jeniya_complete(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """通过 jeniya.top AI 中转站调用大模型，适合无法直连 Google/Anthropic 的服务器。"""
    import requests

    if not PROXY_API_KEY:
        raise ValueError("请在 config.py 中填写 PROXY_API_KEY（jeniya.top API Key）")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    resp = requests.post(
        f"{PROXY_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {PROXY_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or PROXY_MODEL,
            "messages": messages,
            "max_tokens": max_tokens or GEMINI_MAX_TOKENS,
        },
        timeout=120,
        proxies={},  # 不走系统代理，直连中转站
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ---------- Gemini 创作 ----------

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        if not GEMINI_API_KEY:
            raise ValueError("请在 config 或环境变量中设置 GEMINI_API_KEY")
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def gemini_complete(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    根据 config.LLM_PROVIDER 自动路由到对应的大模型：
      - "proxy"   → 中转代理（OpenAI 兼容，推荐服务器使用）
      - "claude"  → Anthropic Claude
      - "gemini"  → Google Gemini（需直连 googleapis.com）

    :param prompt: 用户提示词
    :param system_prompt: 可选，作为前置说明/风格提示
    :param model: 模型 ID（不传则用各 provider 的默认值）
    :param max_tokens: 最大生成长度
    :return: 生成的文本
    """
    if LLM_PROVIDER == "jeniya":
        print(f"[llm] provider=jeniya  model={model or PROXY_MODEL}")
        return _jeniya_complete(prompt, system_prompt=system_prompt, model=model, max_tokens=max_tokens)

    if LLM_PROVIDER == "claude":
        print(f"[llm] provider=claude  model={model or CLAUDE_MODEL}")
        return claude_complete(prompt, system_prompt=system_prompt, model=model, max_tokens=max_tokens)

    # 默认：直连 Gemini
    print(f"[llm] provider=gemini  model={model or GEMINI_MODEL}")
    client = _get_gemini_client()
    contents = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
    resp = client.models.generate_content(
        model=model or GEMINI_MODEL,
        contents=contents,
        config={"max_output_tokens": max_tokens or GEMINI_MAX_TOKENS},
    )
    return resp.text


def gemini_analyze_audio(
    audio_path: str,
    prompt: str,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    将本地音频文件上传到 Gemini Files API，然后结合提示词进行分析，返回文本结果。

    适用场景：让 Gemini 分析音频的实际时间轴，生成带准确时间戳的分镜 JSON。

    :param audio_path: 本地音频文件路径（支持 mp3/wav/m4a 等）
    :param prompt: 分析指令（如"根据此音频生成分镜 JSON"）
    :param model: 模型 ID，建议使用支持音频的 gemini-1.5-flash 或 gemini-1.5-pro
    :param max_tokens: 最大输出 token 数
    :return: Gemini 返回的文本
    """
    import mimetypes
    client = _get_gemini_client()

    # 推断 MIME 类型
    mime_type, _ = mimetypes.guess_type(audio_path)
    if not mime_type:
        mime_type = "audio/mpeg"

    print(f"[gemini] 上传音频文件：{audio_path}（{mime_type}）...")
    uploaded = client.files.upload(
        file=audio_path,
        config={"mime_type": mime_type},
    )
    print(f"[gemini] 上传完成，file_uri={uploaded.uri}")

    # 使用支持音频的模型（flash-lite 不支持音频，需 flash 或 pro）
    audio_model = model or "gemini-1.5-flash"

    from google.genai import types as genai_types
    resp = client.models.generate_content(
        model=audio_model,
        contents=[
            genai_types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime_type),
            prompt,
        ],
        config={"max_output_tokens": max_tokens or GEMINI_MAX_TOKENS},
    )
    return resp.text
