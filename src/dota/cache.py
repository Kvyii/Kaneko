import json
from pathlib import Path

from dota.models.match import MatchDetail

CACHE_DIR = Path(".opendota_cache")


class MatchCache:
    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)

    def _path(self, match_id: int) -> Path:
        return self.cache_dir / f"{match_id}.json"

    def get(self, match_id: int) -> MatchDetail | None:
        path = self._path(match_id)
        if not path.exists():
            return None
        return MatchDetail.model_validate_json(path.read_text())

    def put(self, match_id: int, detail: MatchDetail) -> None:
        """Only cache if the match is parsed (has radiant_gold_adv)."""
        if not detail.radiant_gold_adv:
            return
        path = self._path(match_id)
        path.write_text(detail.model_dump_json())

    def has(self, match_id: int) -> bool:
        return self._path(match_id).exists()
