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
    tower_damage: int = 0
    hero_healing: int = 0
    obs_placed: int = 0
    sen_placed: int = 0
    stuns: float = 0
    lane_efficiency: float | None = None
    gold_per_min: int = 0
    xp_per_min: int = 0
    last_hits: int = 0
    denies: int = 0
    lh_t: list[int] | None = None
    life_state_dead: int = 0
    party_size: int = 1
    net_worth: int = 0
    damage_taken: dict[str, int] | None = None
    kill_streaks: dict[str, int] | None = None
    actions_per_min: int = 0
    teamfight_participation: float = 0

    @property
    def longest_kill_streak(self) -> int:
        if not self.kill_streaks:
            return 0
        return max(int(k) for k in self.kill_streaks)

    @property
    def total_damage_taken(self) -> int:
        if not self.damage_taken:
            return 0
        return sum(self.damage_taken.values())


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
    tower_damage: float | None = None
    damage_taken: float | None = None


class PlayerStats(BaseModel):
    hero_damage: int = 0
    tower_damage: int = 0
    damage_taken: int = 0
    hero_healing: int = 0
    gpm: int = 0
    xpm: int = 0
    last_hits: int = 0
    denies: int = 0
    lh_at_10: int | None = None
    time_dead: int = 0
    net_worth: int = 0
    party_size: int = 1
    longest_kill_streak: int = 0
    apm: int = 0


class ClassifiedMatch(BaseModel):
    match: RecentMatch
    match_type: str
    peak_lead: int | None = None
    peak_deficit: int | None = None
    contribution: Contribution = Contribution()
    stats: PlayerStats = PlayerStats()
    lane: str = "?"
    hero_name: str = "Unknown"
    match_detail: MatchDetail | None = None
