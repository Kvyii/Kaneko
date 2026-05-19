import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("dota.bot.usage")

LOGS_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".logs"
USAGE_FILE = LOGS_DIR / "usage.json"

# Commands that don't count towards the hourly limit
_EXEMPT_COMMANDS = {"usage", "info"}

# Legacy command names to rename in lifetime stats
_COMMAND_RENAMES = {"info": "matches"}


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
                "cmd_hour": "",
                "cmd_count": 0,
                "parse_hour": "",
                "parse_count": 0,
                "api_calls": 0,
                "llm_calls": 0,
                "commands": {},
            }
        return self._data[key]

    def check_command_limit(self, discord_id: int, max_per_hour: int) -> tuple[bool, int]:
        """Returns (allowed, seconds_until_refresh). If allowed, seconds is 0."""
        user = self._ensure_user(discord_id)
        hour = _current_hour()
        if user.get("cmd_hour") != hour:
            return (True, 0)
        if user.get("cmd_count", 0) < max_per_hour:
            return (True, 0)
        return (False, _seconds_until_next_hour())

    def check_parse_limit(self, discord_id: int, max_per_hour: int) -> tuple[bool, int]:
        """Returns (allowed, seconds_until_refresh). If allowed, seconds is 0."""
        user = self._ensure_user(discord_id)
        hour = _current_hour()
        if user.get("parse_hour") != hour:
            return (True, 0)
        if user.get("parse_count", 0) < max_per_hour:
            return (True, 0)
        return (False, _seconds_until_next_hour())

    def record_command(self, discord_id: int, name: str) -> None:
        """Record a command usage. Counts towards hourly limit unless exempt."""
        user = self._ensure_user(discord_id)
        if name not in _EXEMPT_COMMANDS:
            hour = _current_hour()
            if user.get("cmd_hour") != hour:
                user["cmd_hour"] = hour
                user["cmd_count"] = 0
            user["cmd_count"] += 1
        self._record_lifetime(user, name)
        self._save()
        log.debug("Recorded /%s for %d", name, discord_id)

    def record_parse(self, discord_id: int) -> None:
        user = self._ensure_user(discord_id)
        hour = _current_hour()
        if user.get("parse_hour") != hour:
            user["parse_hour"] = hour
            user["parse_count"] = 0
        user["parse_count"] += 1
        self._record_lifetime(user, "parse")
        self._save()
        log.debug("Recorded /parse for %d — count=%d in hour %s", discord_id, user["parse_count"], hour)

    def record_llm(self, discord_id: int) -> None:
        user = self._ensure_user(discord_id)
        user["llm_calls"] = user.get("llm_calls", 0) + 1
        self._save()
        log.debug("Recorded LLM call for %d", discord_id)

    def record_api_calls(self, discord_id: int, count: int) -> None:
        user = self._ensure_user(discord_id)
        user["api_calls"] = user.get("api_calls", 0) + count
        self._save()

    def get_usage(self, discord_id: int) -> dict:
        """Return usage stats for a user."""
        user = self._ensure_user(discord_id)
        hour = _current_hour()
        cmd_this_hour = user.get("cmd_count", 0) if user.get("cmd_hour") == hour else 0
        parse_this_hour = user.get("parse_count", 0) if user.get("parse_hour") == hour else 0

        # Clean up lifetime commands: apply renames and remove exempt
        raw_cmds = dict(user.get("commands", {}))
        cmds: dict[str, int] = {}
        for name, count in raw_cmds.items():
            renamed = _COMMAND_RENAMES.get(name, name)
            if renamed in _EXEMPT_COMMANDS:
                continue
            cmds[renamed] = cmds.get(renamed, 0) + count

        return {
            "commands": cmds,
            "api_calls": user.get("api_calls", 0),
            "llm_calls": user.get("llm_calls", 0),
            "cmd_this_hour": cmd_this_hour,
            "parse_this_hour": parse_this_hour,
            "seconds_until_refresh": _seconds_until_next_hour(),
        }

    def _record_lifetime(self, user: dict, name: str) -> None:
        cmds = user.setdefault("commands", {})
        cmds[name] = cmds.get(name, 0) + 1
