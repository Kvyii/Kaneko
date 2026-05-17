import json
import logging
from pathlib import Path

log = logging.getLogger("dota.bot.players")

PLAYERS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "players.json"


class PlayerRegistry:
    def __init__(self, path: Path = PLAYERS_FILE) -> None:
        self._path = path
        self._data: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            self._data = json.loads(self._path.read_text())
            log.info("Loaded %d player registrations from %s", len(self._data), self._path)
        else:
            log.info("No players file found at %s — starting fresh", self._path)

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._data, indent=2))
        log.debug("Saved %d registrations to %s", len(self._data), self._path)

    def get(self, discord_id: int) -> int | None:
        return self._data.get(str(discord_id))

    def register(self, discord_id: int, player_id: int) -> None:
        self._data[str(discord_id)] = player_id
        self._save()
        log.info("Registered discord_id=%d -> player_id=%d", discord_id, player_id)
