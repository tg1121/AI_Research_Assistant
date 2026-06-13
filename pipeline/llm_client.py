"""
Unified LLM client using LiteLLM.
Model string format: "provider/model-name" e.g. "groq/llama-3.3-70b-versatile"
"""

import os
import requests
import litellm
from litellm.exceptions import AuthenticationError, RateLimitError

litellm.telemetry = False
litellm._turn_on_debug()


# ── provider catalogue ────────────────────────────────────────────────

PROVIDERS = {
    "Ollama (local)": {
        "prefix":       "ollama",
        "default_model":"ollama/llama3.2",
        "env_var":      "",
        "key_hint":     "(no key needed)",
        "notes":        "Runs locally via Ollama. Start with: ollama serve",
        "models": [
            "ollama/llama3.2",
            "ollama/llama3.1:8b",
            "ollama/llama3.1:70b",
            "ollama/qwen2.5:7b",
            "ollama/qwen2.5:14b",
            "ollama/mistral",
            "ollama/deepseek-r1:8b",
            "ollama/phi4",
        ],
    },
    "Google Gemini": {
        "prefix":       "gemini",
        "default_model":"gemini/gemini-2.0-flash",
        "env_var":      "GEMINI_API_KEY",
        "key_hint":     "AIza...",
        "notes":        "Free tier: 1,500 req/day. Get key: aistudio.google.com",
        "models": [
            "gemini/gemini-2.0-flash",
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.0-flash-lite",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
            "gemini/gemini-2.5-pro",
        ],
    },
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
        "default_model":"openai/gpt-oss-120b:free",
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


def fetch_groq_models(api_key: str | None = None) -> list[str]:
    """Fetch live model list from Groq API."""
    FALLBACK = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ]
    try:
        key = api_key or os.environ.get("GROQ_API_KEY", "")
        if not key:
            return FALLBACK
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        ids = sorted(m["id"] for m in data if m.get("id"))
        return ids if ids else FALLBACK
    except Exception:
        return FALLBACK


def fetch_openai_models(api_key: str | None = None) -> list[str]:
    """Fetch live GPT model list from OpenAI API (chat-capable only)."""
    FALLBACK = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
    try:
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            return FALLBACK
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        ids = sorted(m["id"] for m in data if m.get("id") and "gpt" in m.get("id", ""))
        return ids if ids else FALLBACK
    except Exception:
        return FALLBACK


def fetch_anthropic_models(api_key: str | None = None) -> list[str]:
    """Fetch live model list from Anthropic API."""
    FALLBACK = [
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
    ]
    try:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return FALLBACK
        resp = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        ids = sorted(m["id"] for m in data if m.get("id"))
        return ids if ids else FALLBACK
    except Exception:
        return FALLBACK


def fetch_gemini_models(api_key: str | None = None) -> list[str]:
    """Fetch live Gemini model list from Google AI API."""
    FALLBACK = [
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.0-flash-lite",
        "gemini/gemini-1.5-flash",
        "gemini/gemini-1.5-pro",
        "gemini/gemini-2.5-pro",
    ]
    try:
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            return FALLBACK
        resp = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json().get("models", [])
        ids = sorted(
            f"gemini/{m['name'].split('/')[-1]}"
            for m in data
            if "generateContent" in m.get("supportedGenerationMethods", [])
        )
        return ids if ids else FALLBACK
    except Exception:
        return FALLBACK


def fetch_mistral_models(api_key: str | None = None) -> list[str]:
    """Fetch live model list from Mistral API."""
    FALLBACK = [
        "mistral/mistral-small-latest",
        "mistral/mistral-medium-latest",
        "mistral/mistral-large-latest",
        "mistral/codestral-latest",
    ]
    try:
        key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        if not key:
            return FALLBACK
        resp = requests.get(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        ids = sorted(f"mistral/{m['id']}" for m in data if m.get("id"))
        return ids if ids else FALLBACK
    except Exception:
        return FALLBACK


def fetch_ollama_models(api_key: str | None = None) -> list[str]:
    """Fetch locally installed models from a running Ollama server."""
    FALLBACK = PROVIDERS["Ollama (local)"]["models"]
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        resp.raise_for_status()
        data = resp.json().get("models", [])
        ids = [f"ollama/{m['name']}" for m in data if m.get("name")]
        return ids if ids else FALLBACK
    except Exception:
        return FALLBACK


def fetch_provider_models(prefix: str, api_key: str | None = None) -> list[str]:
    """Dispatch to the correct per-provider fetch function."""
    dispatch = {
        "ollama":     fetch_ollama_models,
        "openrouter": fetch_openrouter_free_models,
        "groq":       fetch_groq_models,
        "openai":     fetch_openai_models,
        "anthropic":  fetch_anthropic_models,
        "gemini":     fetch_gemini_models,
        "mistral":    fetch_mistral_models,
    }
    fn = dispatch.get(prefix)
    return fn(api_key) if fn else []


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
        if model.startswith("ollama/"):
            kwargs["api_base"] = "http://localhost:11434"

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
