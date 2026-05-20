import logging
import os
import re
from datetime import datetime
from pathlib import Path

import httpx

log = logging.getLogger("dota.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LOG_DIR = Path(".llm_logs")

# Section headers the prompt asks for (case-insensitive match)
_SECTION_PATTERN = re.compile(
    r"^#\s+(Match Summary|Player Performance Analysis|Core Reasons|Rivals)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_HEADER_TO_KEY = {
    "match summary": "match_summary",
    "player performance analysis": "player_performance",
    "core reasons": "core_reasons",
    "rivals": "rivals",
}


def _log_prompt(system_prompt: str) -> None:
    """Log the sent prompt to a timestamped file."""
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = LOG_DIR / f"{timestamp}.txt"
    path.write_text(system_prompt, encoding="utf-8")


def _parse_response(content: str) -> dict[str, str]:
    """Split the markdown response by # headings into sections."""
    sections: dict[str, str] = {
        "match_summary": "",
        "player_performance": "",
        "core_reasons": "",
        "rivals": "",
    }

    # Find all section header positions
    matches = list(_SECTION_PATTERN.finditer(content))

    if not matches:
        # No headers found — return everything as match_summary
        sections["match_summary"] = content.strip()
        return sections

    for i, m in enumerate(matches):
        header = m.group(1).lower()
        key = _HEADER_TO_KEY.get(header)
        if not key:
            continue

        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections[key] = content[start:end].strip()

    return sections


def analyze_match(system_prompt: str) -> dict[str, str]:
    """Send the fully-assembled system prompt to an LLM via OpenRouter.

    Returns a dict with keys: match_summary, player_performance, core_reasons.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    if not api_key or api_key == "sk-your-key-here":
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )

    _log_prompt(system_prompt)

    log.info("POST %s — model=%s, prompt_len=%d chars", OPENROUTER_URL, model, len(system_prompt))
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
    log.info("OpenRouter response — %d", response.status_code)
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    log.info("LLM response — %d chars, parsing sections", len(content))
    result = _parse_response(content)
    log.info("Parsed sections — %s", {k: len(v) for k, v in result.items()})
    return result
