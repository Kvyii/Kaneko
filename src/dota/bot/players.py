import json
import logging
from pathlib import Path

log = logging.getLogger("dota.bot.players")

PLAYERS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "players.json"

DEFAULT_MAX_INFO_PER_HOUR = 5
DEFAULT_MAX_LLM_PER_HOUR = 3


class PlayerRegistry:
    def __init__(self, path: Path = PLAYERS_FILE) -> None:
        self._path = path
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            migrated = False
            for key, value in raw.items():
                if isinstance(value, int):
                    # Auto-migrate old format: discord_id -> player_id
                    raw[key] = {
                        "player_id": value,
                        "max_llm_per_hour": DEFAULT_MAX_LLM_PER_HOUR,
                        "max_info_per_hour": DEFAULT_MAX_INFO_PER_HOUR,
                    }
                    migrated = True
            self._data = raw
            if migrated:
                log.info("Migrated %d entries to new format", len(self._data))
                self._save()
            log.info("Loaded %d player registrations from %s", len(self._data), self._path)
        else:
            log.info("No players file found at %s — starting fresh", self._path)

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._data, indent=2))
        log.debug("Saved %d registrations to %s", len(self._data), self._path)

    def get(self, discord_id: int) -> int | None:
        entry = self._data.get(str(discord_id))
        if entry is None:
            return None
        return entry["player_id"]

    def get_limits(self, discord_id: int) -> tuple[int, int]:
        """Returns (max_info_per_hour, max_llm_per_hour)."""
        entry = self._data.get(str(discord_id))
        if entry is None:
            return (DEFAULT_MAX_INFO_PER_HOUR, DEFAULT_MAX_LLM_PER_HOUR)
        return (
            entry.get("max_info_per_hour", DEFAULT_MAX_INFO_PER_HOUR),
            entry.get("max_llm_per_hour", DEFAULT_MAX_LLM_PER_HOUR),
        )

    def register(self, discord_id: int, player_id: int) -> None:
        self._data[str(discord_id)] = {
            "player_id": player_id,
            "max_llm_per_hour": DEFAULT_MAX_LLM_PER_HOUR,
            "max_info_per_hour": DEFAULT_MAX_INFO_PER_HOUR,
        }
        self._save()
        log.info("Registered discord_id=%d -> player_id=%d", discord_id, player_id)
