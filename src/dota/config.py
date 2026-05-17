import json
from pathlib import Path

from pydantic import BaseModel


class Config(BaseModel):
    player_id: int
    turbo_only: bool = False


def load_config(path: Path | None = None) -> Config:
    if path is None:
        path = Path("config.json")
    with open(path) as f:
        data = json.load(f)
    return Config(**data)
