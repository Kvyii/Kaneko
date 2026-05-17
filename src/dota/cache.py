import json
from pathlib import Path

from dota.models.match import MatchDetail

CACHE_DIR = Path(".opendota_cache")

# Fields to strip from the raw API response before caching
_EXCLUDED_TOP_LEVEL = {"cosmetics", "draft_timings", "chat", "pauses", "version"}
_EXCLUDED_PLAYER = {
    "cosmetics", "lane_pos", "actions", "pings", "connection_log",
    "ability_targets", "hero_hits", "item_win", "item_usage",
    "benchmarks", "gold_reasons", "xp_reasons", "purchase",
}


def _clean_raw(data: dict) -> dict:
    """Remove noisy/cosmetic fields from the raw API response."""
    cleaned = {k: v for k, v in data.items() if k not in _EXCLUDED_TOP_LEVEL}
    if "players" in cleaned:
        cleaned["players"] = [
            {k: v for k, v in p.items() if k not in _EXCLUDED_PLAYER}
            for p in cleaned["players"]
        ]
    return cleaned


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
        data = json.loads(path.read_text())
        return MatchDetail(**data)

    def get_raw(self, match_id: int) -> dict | None:
        """Get the full cached raw JSON for LLM consumption."""
        path = self._path(match_id)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def put_raw(self, match_id: int, raw_data: dict) -> None:
        """Cache cleaned raw API response. Only caches parsed matches."""
        if not raw_data.get("radiant_gold_adv"):
            return
        cleaned = _clean_raw(raw_data)
        path = self._path(match_id)
        path.write_text(json.dumps(cleaned, indent=2))

    def has(self, match_id: int) -> bool:
        return self._path(match_id).exists()
