"""Provider-agnostic LLM gateway — free tiers first (Gemini / GitHub Models).
Returns plain text or None; callers fall back to the deterministic bilingual
brain so the product never breaks without keys."""
import httpx

from .config import SETTINGS


def llm_available() -> bool:
    return bool(SETTINGS.gemini_api_key or SETTINGS.github_token
                or SETTINGS.openai_api_key or SETTINGS.anthropic_api_key
                or SETTINGS.openrouter_api_key)


def complete(system: str, user: str, temperature: float = 0.3, max_tokens: int = 500) -> str | None:
    try:
        if SETTINGS.gemini_api_key:
            return _gemini(system, user, temperature, max_tokens)
        if SETTINGS.github_token:
            return _openai(system, user, temperature, max_tokens,
                           base="https://models.inference.ai.azure.com",
                           model=SETTINGS.llm_model or "gpt-4o-mini",
                           key=SETTINGS.github_token)
        if SETTINGS.openai_api_key:
            return _openai(system, user, temperature, max_tokens)
        if SETTINGS.anthropic_api_key:
            return _anthropic(system, user, temperature, max_tokens)
        if SETTINGS.openrouter_api_key:
            return _openai(system, user, temperature, max_tokens,
                           base="https://openrouter.ai/api/v1",
                           model=SETTINGS.llm_model or "openai/gpt-4o-mini",
                           key=SETTINGS.openrouter_api_key)
    except Exception:
        return None
    return None


def _openai(system, user, temperature, max_tokens, base="https://api.openai.com/v1",
            model=None, key=None):
    r = httpx.post(f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key or SETTINGS.openai_api_key}"},
        json={"model": model or SETTINGS.llm_model or "gpt-4o-mini",
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}],
              "temperature": temperature, "max_tokens": max_tokens}, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _anthropic(system, user, temperature, max_tokens):
    r = httpx.post("https://api.anthropic.com/v1/messages",
        headers={"x-api-key": SETTINGS.anthropic_api_key, "anthropic-version": "2023-06-01"},
        json={"model": SETTINGS.llm_model or "claude-sonnet-4-20250514",
              "max_tokens": max_tokens, "temperature": temperature,
              "system": system, "messages": [{"role": "user", "content": user}]}, timeout=60)
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def _gemini(system, user, temperature, max_tokens):
    model = SETTINGS.llm_model or "gemini-2.0-flash"
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={SETTINGS.gemini_api_key}",
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"parts": [{"text": user}]}],
              "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}},
        timeout=60)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
