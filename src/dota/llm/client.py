import os
from datetime import datetime
from pathlib import Path

import httpx


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LOG_DIR = Path(".llm_logs")


def _log_prompt(system_prompt: str) -> None:
    """Log the sent prompt to a timestamped file."""
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = LOG_DIR / f"{timestamp}.txt"
    path.write_text(system_prompt, encoding="utf-8")


def analyze_match(system_prompt: str) -> str:
    """Send the fully-assembled system prompt to an LLM via OpenRouter.

    This is a pure data-in/data-out function with no display logic.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    if not api_key or api_key == "sk-your-key-here":
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )

    _log_prompt(system_prompt)

    response = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Analyse this match."},
            ],
        },
        timeout=60.0,
    )
    response.raise_for_status()

    data = response.json()
    return data["choices"][0]["message"]["content"]
