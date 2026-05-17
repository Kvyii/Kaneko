from dota.models.match import (
    ClassifiedMatch,
    Contribution,
    MatchDetail,
    PlayerDetail,
    PlayerStats,
    RecentMatch,
)


def find_player(detail: MatchDetail, player_slot: int) -> PlayerDetail | None:
    for p in detail.players:
        if p.player_slot == player_slot:
            return p
    return None


def classify_match(
    match: RecentMatch, detail: MatchDetail | None
) -> tuple[str, int | None, int | None]:
    """Classify match into Stomp/Stomped/Comeback/Throw/Even. Returns (type, max_lead, max_deficit)."""
    if detail is None or not detail.radiant_gold_adv:
        return ("-", None, None)

    team_adv = (
        detail.radiant_gold_adv
        if match.is_radiant
        else [-v for v in detail.radiant_gold_adv]
    )
    max_lead = max(team_adv)
    max_deficit = min(team_adv)

    swing = max_lead + abs(max_deficit) if max_deficit < 0 else max_lead
    lead_pct = max_lead / swing if swing > 0 else 0
    deficit_pct = abs(max_deficit) / swing if swing > 0 else 0

    if match.won:
        if max_deficit < -5000 and deficit_pct >= 0.5:
            match_type = "Comeback"
        elif max_lead > 8000 and lead_pct >= 0.5:
            match_type = "Stomp"
        else:
            match_type = "Even"
    else:
        if max_lead > 5000 and lead_pct >= 0.5:
            match_type = "Throw"
        elif max_deficit < -8000 and deficit_pct >= 0.5:
            match_type = "Stomped"
        else:
            match_type = "Even"

    return (match_type, max_lead, max_deficit)


def compute_contribution(
    match: RecentMatch, detail: MatchDetail | None
) -> Contribution:
    contrib = Contribution()
    if detail is None:
        return contrib

    player = find_player(detail, match.player_slot)
    if player is None:
        return contrib

    teammates = [
        p for p in detail.players if (p.player_slot < 128) == match.is_radiant
    ]
    if not teammates:
        return contrib

    # Fight: (kills + assists) / team total kills
    team_kills = sum(p.kills for p in teammates)
    if team_kills > 0:
        contrib.fight = (player.kills + player.assists) / team_kills * 100

    # Damage: hero_damage / team total
    team_damage = sum(p.hero_damage for p in teammates)
    if team_damage > 0:
        contrib.damage = player.hero_damage / team_damage * 100

    # Vision: (obs + sen placed) / team total
    player_vision = player.obs_placed + player.sen_placed
    team_vision = sum(p.obs_placed + p.sen_placed for p in teammates)
    if team_vision > 0:
        contrib.vision = player_vision / team_vision * 100

    # Stuns: stun duration / team total
    team_stuns = sum(p.stuns for p in teammates)
    if team_stuns > 0:
        contrib.stuns = player.stuns / team_stuns * 100

    # Lane efficiency
    if player.lane_efficiency is not None:
        contrib.lane_eff = player.lane_efficiency * 100

    return contrib


def get_lane(match: RecentMatch, detail: MatchDetail | None) -> str:
    if detail is None:
        return "?"
    player = find_player(detail, match.player_slot)
    if player is None or player.lane is None:
        return "?"
    if match.is_radiant:
        lane_map = {1: "Safe", 2: "Mid", 3: "Off"}
    else:
        lane_map = {1: "Off", 2: "Mid", 3: "Safe"}
    return lane_map.get(player.lane, "?")


def get_player_stats(match: RecentMatch, detail: MatchDetail | None) -> PlayerStats:
    if detail is None:
        return PlayerStats()
    player = find_player(detail, match.player_slot)
    if player is None:
        return PlayerStats()
    lh_at_10 = None
    if player.lh_t and len(player.lh_t) > 10:
        lh_at_10 = player.lh_t[10]

    return PlayerStats(
        tower_damage=player.tower_damage,
        hero_healing=player.hero_healing,
        gpm=player.gold_per_min,
        xpm=player.xp_per_min,
        last_hits=player.last_hits,
        denies=player.denies,
        lh_at_10=lh_at_10,
        time_dead=player.life_state_dead,
    )


def build_classified_matches(
    matches: list[RecentMatch],
    details: dict[int, MatchDetail],
    heroes: dict[str, str],
) -> list[ClassifiedMatch]:
    results = []
    for match in matches:
        detail = details.get(match.match_id)
        match_type, peak_lead, peak_deficit = classify_match(match, detail)
        contribution = compute_contribution(match, detail)
        lane = get_lane(match, detail)
        hero_name = heroes.get(str(match.hero_id), f"ID:{match.hero_id}")

        stats = get_player_stats(match, detail)

        results.append(
            ClassifiedMatch(
                match=match,
                match_type=match_type,
                peak_lead=peak_lead,
                peak_deficit=peak_deficit,
                contribution=contribution,
                stats=stats,
                lane=lane,
                hero_name=hero_name,
                match_detail=detail,
            )
        )
    return results
