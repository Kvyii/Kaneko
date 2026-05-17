from pydantic import BaseModel


class RecentMatch(BaseModel):
    match_id: int
    player_slot: int
    radiant_win: bool
    hero_id: int
    kills: int
    deaths: int
    assists: int
    duration: int
    start_time: int

    @property
    def is_radiant(self) -> bool:
        return self.player_slot < 128

    @property
    def won(self) -> bool:
        return self.is_radiant == self.radiant_win


class PlayerDetail(BaseModel):
    player_slot: int
    lane: int | None = None
    kills: int = 0
    assists: int = 0
    hero_damage: int = 0
    obs_placed: int = 0
    sen_placed: int = 0
    stuns: float = 0
    lane_efficiency: float | None = None


class MatchDetail(BaseModel):
    match_id: int
    radiant_gold_adv: list[int] | None = None
    players: list[PlayerDetail] = []


class Contribution(BaseModel):
    fight: float | None = None
    damage: float | None = None
    vision: float | None = None
    stuns: float | None = None
    lane_eff: float | None = None


class ClassifiedMatch(BaseModel):
    match: RecentMatch
    match_type: str
    peak_lead: int | None = None
    peak_deficit: int | None = None
    contribution: Contribution = Contribution()
    lane: str = "?"
    hero_name: str = "Unknown"
