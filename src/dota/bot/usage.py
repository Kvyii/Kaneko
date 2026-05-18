import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("dota.bot.usage")

LOGS_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".logs"
USAGE_FILE = LOGS_DIR / "usage.json"


def _current_hour() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H")


def _seconds_until_next_hour() -> int:
    now = datetime.now()
    seconds_into_hour = now.minute * 60 + now.second
    return 3600 - seconds_into_hour


class UsageTracker:
    def __init__(self, path: Path = USAGE_FILE) -> None:
        self._path = path
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            self._data = json.loads(self._path.read_text())
            log.info("Loaded usage data for %d users from %s", len(self._data), self._path)
        else:
            log.info("No usage file found at %s — starting fresh", self._path)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    def _ensure_user(self, discord_id: int) -> dict:
        key = str(discord_id)
        if key not in self._data:
            self._data[key] = {
                "info_hour": "",
                "info_count": 0,
                "llm_hour": "",
                "llm_count": 0,
                "api_calls": 0,
                "llm_calls": 0,
                "commands": {},
            }
        return self._data[key]

    def check_info_limit(self, discord_id: int, max_per_hour: int) -> tuple[bool, int]:
        """Returns (allowed, seconds_until_refresh). If allowed, seconds is 0."""
        user = self._ensure_user(discord_id)
        hour = _current_hour()
        if user.get("info_hour") != hour:
            return (True, 0)
        if user.get("info_count", 0) < max_per_hour:
            return (True, 0)
        return (False, _seconds_until_next_hour())

    def check_llm_limit(self, discord_id: int, max_per_hour: int) -> tuple[bool, int]:
        """Returns (allowed, seconds_until_refresh). If allowed, seconds is 0."""
        user = self._ensure_user(discord_id)
        hour = _current_hour()
        if user.get("llm_hour") != hour:
            return (True, 0)
        if user.get("llm_count", 0) < max_per_hour:
            return (True, 0)
        return (False, _seconds_until_next_hour())

    def record_info(self, discord_id: int) -> None:
        user = self._ensure_user(discord_id)
        hour = _current_hour()
        if user.get("info_hour") != hour:
            user["info_hour"] = hour
            user["info_count"] = 0
        user["info_count"] += 1
        self._record_command(user, "info")
        self._save()
        log.debug("Recorded /info for %d — count=%d in hour %s", discord_id, user["info_count"], hour)

    def record_llm(self, discord_id: int) -> None:
        user = self._ensure_user(discord_id)
        hour = _current_hour()
        if user.get("llm_hour") != hour:
            user["llm_hour"] = hour
            user["llm_count"] = 0
        user["llm_count"] += 1
        user["llm_calls"] = user.get("llm_calls", 0) + 1
        self._save()
        log.debug("Recorded LLM call for %d — count=%d in hour %s", discord_id, user["llm_count"], hour)

    def record_api_calls(self, discord_id: int, count: int) -> None:
        user = self._ensure_user(discord_id)
        user["api_calls"] = user.get("api_calls", 0) + count
        self._save()

    def record_command(self, discord_id: int, name: str) -> None:
        user = self._ensure_user(discord_id)
        self._record_command(user, name)
        self._save()

    def get_usage(self, discord_id: int) -> dict:
        """Return usage stats for a user: commands, api_calls, current hour counts."""
        user = self._ensure_user(discord_id)
        hour = _current_hour()
        info_this_hour = user.get("info_count", 0) if user.get("info_hour") == hour else 0
        llm_this_hour = user.get("llm_count", 0) if user.get("llm_hour") == hour else 0
        return {
            "commands": dict(user.get("commands", {})),
            "api_calls": user.get("api_calls", 0),
            "llm_calls": user.get("llm_calls", 0),
            "info_this_hour": info_this_hour,
            "llm_this_hour": llm_this_hour,
            "seconds_until_refresh": _seconds_until_next_hour(),
        }

    def _record_command(self, user: dict, name: str) -> None:
        cmds = user.setdefault("commands", {})
        cmds[name] = cmds.get(name, 0) + 1
