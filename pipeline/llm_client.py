"""
Unified LLM client using LiteLLM.
Model string format: "provider/model-name" e.g. "groq/llama-3.3-70b-versatile"
"""

import os
import requests
import litellm
from litellm.exceptions import AuthenticationError, RateLimitError

litellm.telemetry = False


# ── provider catalogue ────────────────────────────────────────────────

PROVIDERS = {
    "Groq (free tier)": {
        "prefix":       "groq",
        "default_model":"llama-3.3-70b-versatile",
        "env_var":      "GROQ_API_KEY",
        "key_hint":     "gsk_...",
        "notes":        "100k tokens/day free. Get key: console.groq.com/keys",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama-3.1-70b-versatile",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
    },
    "OpenRouter (free models)": {
        "prefix":       "openrouter",
        "default_model":"meta-llama/llama-3.3-70b-instruct:free",
        "env_var":      "OPENROUTER_API_KEY",
        "key_hint":     "sk-or-...",
        "notes":        "One key routes to GPT, Claude, Gemini, Llama and more. Append :free for free-tier models.",
        "models": [],   # populated dynamically from OpenRouter API
    },
    "OpenAI": {
        "prefix":       "openai",
        "default_model":"gpt-4o-mini",
        "env_var":      "OPENAI_API_KEY",
        "key_hint":     "sk-...",
        "notes":        "Paid. gpt-4o-mini is cheapest.",
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ],
    },
    "Anthropic": {
        "prefix":       "anthropic",
        "default_model":"claude-haiku-4-5-20251001",
        "env_var":      "ANTHROPIC_API_KEY",
        "key_hint":     "sk-ant-...",
        "notes":        "Paid. claude-haiku is cheapest.",
        "models": [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
        ],
    },
    "Google Gemini": {
        "prefix":       "gemini",
        "default_model":"gemini/gemini-1.5-flash",
        "env_var":      "GEMINI_API_KEY",
        "key_hint":     "AIza...",
        "notes":        "Free tier available. Get key: aistudio.google.com",
        "models": [
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
            "gemini/gemini-2.0-flash",
            "gemini/gemini-2.5-pro",
        ],
    },
    "Mistral": {
        "prefix":       "mistral",
        "default_model":"mistral/mistral-small-latest",
        "env_var":      "MISTRAL_API_KEY",
        "key_hint":     "...",
        "notes":        "Paid. mistral-small is cheapest.",
        "models": [
            "mistral/mistral-small-latest",
            "mistral/mistral-medium-latest",
            "mistral/mistral-large-latest",
            "mistral/codestral-latest",
        ],
    },
}


def fetch_openrouter_free_models(api_key: str | None = None) -> list[str]:
    """
    Fetch the live list of free models from OpenRouter's public API.
    A model is free if its id ends with ':free' OR both prompt+completion cost are 0.
    Falls back to a hardcoded list on failure.
    """
    FALLBACK = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "google/gemma-3-27b-it:free",
        "mistralai/mistral-7b-instruct:free",
        "deepseek/deepseek-r1:free",
        "deepseek/deepseek-v3:free",
        "qwen/qwen3-235b-a22b:free",
        "qwen/qwen3-30b-a3b:free",
        "microsoft/phi-4-reasoning:free",
        "openrouter/auto",
    ]
    try:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])

        free = []
        for m in data:
            model_id = m.get("id", "")
            # primary signal: id ends with :free
            if model_id.endswith(":free"):
                free.append(model_id)
                continue
            # secondary: pricing explicitly zero
            pricing = m.get("pricing", {})
            try:
                prompt_cost = float(pricing.get("prompt", "1") or "1")
                completion_cost = float(pricing.get("completion", "1") or "1")
                if prompt_cost == 0 and completion_cost == 0:
                    free.append(model_id)
            except (ValueError, TypeError):
                continue

        return sorted(free) if free else FALLBACK
    except Exception:
        return FALLBACK


# ── public API ────────────────────────────────────────────────────────

class DailyTokenLimitError(Exception):
    pass

class InvalidAPIKeyError(Exception):
    pass


def resolve_model(provider_label: str,
                  model_override: str | None = None) -> str:
    """Build the full litellm model string for a provider + model name."""
    info = PROVIDERS[provider_label]
    raw = (model_override or info["default_model"]).strip()
    prefix = info["prefix"]
    # OpenRouter models contain a "/" in their own name (e.g. "google/gemma-4-26b:free")
    # so we can't use "/" as a signal that the prefix is already there.
    # Instead, check if the string already starts with the correct provider prefix.
    if raw.startswith(f"{prefix}/"):
        return raw  # already fully qualified
    if "/" in raw and prefix == "openrouter":
        # bare OpenRouter model id like "google/gemma-4-26b:free" — must prepend
        return f"openrouter/{raw}"
    if "/" in raw:
        return raw  # genuinely another provider's fully-qualified string
    return f"{prefix}/{raw}"


def clean_json(raw: str | None, context: str = "") -> str:
    """Strip markdown fences from an LLM JSON response. Raises clearly if raw is None."""
    if raw is None:
        raise ValueError(f"LLM returned null content{f' ({context})' if context else ''}. "
                         "The model may have refused, hit a token limit, or be unsupported.")
    return raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def llm_call(messages: list,
             model: str,
             api_key: str | None = None,
             max_tokens: int = 1024) -> str:
    """
    Make a chat completion call via LiteLLM.
    model and api_key are passed explicitly — no hidden global state.
    """
    try:
        kwargs = dict(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
        )
        if api_key:
            kwargs["api_key"] = api_key

        response = litellm.completion(**kwargs)
        content = response.choices[0].message.content
        if content is None:
            raise ValueError(f"Model '{model}' returned null content — it may have refused or hit a limit.")
        return content

    except AuthenticationError as e:
        raise InvalidAPIKeyError(
            "API key rejected — please check your key and try again."
        ) from e

    except RateLimitError as e:
        msg = str(e)
        if any(t in msg for t in ("per day", "TPD", "daily", "quota", "exceeded")):
            raise DailyTokenLimitError(
                "Daily token limit reached. Try again tomorrow or switch provider/key."
            ) from e
        raise DailyTokenLimitError(f"Rate limit hit: {msg}") from e
