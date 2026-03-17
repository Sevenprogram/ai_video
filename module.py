"""
大模型调用模块：根据 config.LLM_PROVIDER 调用对应 API 完成补全。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    LLM_PROVIDER,
    PROXY_API_KEY,
    PROXY_BASE_URL,
    PROXY_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MAX_TOKENS,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_MAX_TOKENS,
    ELEVENLABS_API_KEY,
    DEFAULT_VOICE_ID,
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
)


def gemini_complete(prompt: str) -> str:
    """
    调用大模型完成补全，返回生成的文本。
    根据 LLM_PROVIDER 选择 jeniya/gemini/claude。
    """
    if LLM_PROVIDER == "jeniya":
        return _jeniya_complete(prompt)
    if LLM_PROVIDER == "gemini":
        return _gemini_complete(prompt)
    if LLM_PROVIDER == "claude":
        return _claude_complete(prompt)
    return _jeniya_complete(prompt)


def _jeniya_complete(prompt: str) -> str:
    """通过 Jeniya 中转站调用 Gemini 2.0 Flash（使用 OpenAI 兼容协议的 HTTP 客户端，请求发往 jeniya.top 而非 api.openai.com）。"""
    import openai
    client = openai.OpenAI(
        api_key=PROXY_API_KEY,
        base_url=PROXY_BASE_URL,
    )
    r = client.chat.completions.create(
        model=PROXY_MODEL,  # gemini-2.0-flash（Jeniya 侧模型）
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )
    return (r.choices[0].message.content or "").strip()


def _gemini_complete(prompt: str) -> str:
    """直连 Google Gemini API。"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        r = model.generate_content(prompt)
        return (r.text or "").strip()
    except Exception as e:
        raise RuntimeError(f"Gemini 调用失败: {e}")


def gemini_complete_only(prompt: str) -> str:
    """始终使用 config 中的 Gemini（GEMINI_API_KEY/GEMINI_MODEL），不随 LLM_PROVIDER 切换。"""
    return _gemini_complete(prompt)


def jeniya_complete_only(prompt: str) -> str:
    """始终使用 config 中的 Jeniya 中转站（PROXY_*），不随 LLM_PROVIDER 切换。"""
    return _jeniya_complete(prompt)


def _claude_complete(prompt: str) -> str:
    """直连 Anthropic Claude API。"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        r = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        if r.content and len(r.content) > 0:
            return r.content[0].text.strip()
        return ""
    except Exception as e:
        raise RuntimeError(f"Claude 调用失败: {e}")


def text_to_speech_to_file(text: str, output_path: str) -> None:
    """调用 ElevenLabs API 将文本转为语音，保存为音频文件。"""
    import requests
    url = "https://api.elevenlabs.io/v1/text-to-speech/" + DEFAULT_VOICE_ID
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": DEFAULT_MODEL_ID,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
    }
    r = requests.post(url, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    d = os.path.dirname(output_path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(r.content)
