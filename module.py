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
    """通过 Jeniya 中转站（OpenAI 兼容接口）调用。"""
    import openai
    client = openai.OpenAI(
        api_key=PROXY_API_KEY,
        base_url=PROXY_BASE_URL,
    )
    r = client.chat.completions.create(
        model=PROXY_MODEL,
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
