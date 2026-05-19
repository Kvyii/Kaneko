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


def _curve_metrics(
    team_adv: list[int],
) -> tuple[float, float, int, bool, bool]:
    """Compute curve-shape metrics from the gold advantage timeline.

    Analyses the gold advantage curve from the player's team perspective,
    skipping the first 5 minutes (laning phase where gold is naturally close).

    For each minute after the skip window, a minute counts as "meaningfully
    ahead" or "behind" only if the advantage exceeds a per-minute scaling
    threshold of ``(minute + 1) * 75`` gold.  This naturally filters early-game
    noise and scales with game length / turbo inflation.

    Reversals are counted after the same skip window: each time the
    advantage crosses from one significant side to the other counts as
    one reversal.  A higher per-minute threshold of ``(minute + 1) * 400``
    gold is used (e.g. 4k at min 10, 12k at min 30) so that normal
    mid-game fluctuations don't register as chaotic swings.

    A peak fallback checks whether the advantage at any minute after
    minute 15 exceeded ``minute * 800`` gold (e.g. 12k at min 15,
    24k at min 30).  This catches games where a massive lead/deficit
    occurred but the ratio alone doesn't reflect it because the game
    swung back the other way.

    Returns:
        pct_ahead:      Fraction of post-skip minutes meaningfully ahead (0-1).
        pct_behind:     Fraction of post-skip minutes meaningfully behind (0-1).
        reversals:      Number of significant lead changes after the skip window.
        peak_lead:      True if the lead at any minute after 15 exceeded
                        that minute * 800 gold.
        peak_deficit:   True if the deficit at any minute after 15 exceeded
                        that minute * 800 gold.
    """
    skip = 5
    factor = 75

    # --- dominance percentages (skip early laning) ---
    analysis = team_adv[skip:] if len(team_adv) > skip else team_adv
    ahead = 0
    behind = 0
    for i, val in enumerate(analysis):
        t = i + skip
        thresh = (t + 1) * factor
        if val > thresh:
            ahead += 1
        elif val < -thresh:
            behind += 1
    total = len(analysis)
    pct_ahead = ahead / total if total > 0 else 0.0
    pct_behind = behind / total if total > 0 else 0.0

    # --- reversals (skip early laning, higher threshold than dominance) ---
    rev_factor = 400
    reversals = 0
    last_side = 0  # +1 = ahead, -1 = behind
    for t, val in enumerate(team_adv):
        if t < skip:
            continue
        thresh = (t + 1) * rev_factor
        if val > thresh:
            side = 1
        elif val < -thresh:
            side = -1
        else:
            continue
        if last_side != 0 and side != last_side:
            reversals += 1
        last_side = side

    # --- peak fallback (was the lead/deficit extreme at any point?) ---
    peak_gpm = 800
    peak_min_minute = 15
    peak_lead = False
    peak_deficit = False
    for t, val in enumerate(team_adv):
        if t < peak_min_minute:
            continue
        if val > t * peak_gpm:
            peak_lead = True
        if val < -(t * peak_gpm):
            peak_deficit = True

    return pct_ahead, pct_behind, reversals, peak_lead, peak_deficit


def classify_match(
    match: RecentMatch, detail: MatchDetail | None
) -> tuple[str, int | None, int | None]:
    """Classify a match by analysing the shape of the gold advantage curve.

    Categories (checked in this order):

    1. **Chaotic** — 3+ significant reversals regardless of outcome.
       The game swung back and forth too many times to be a clean anything.

    2. **Stomp / Stomped** — One side was meaningfully ahead for 2x+ more
       time than the other. Stomp if the dominant side won, Stomped if lost.

    3. **Comeback / Throw** — Same 2x ratio but on the *losing* side of
       the curve. Comeback if won despite being behind, Throw if lost
       despite being ahead.

    4. **Peak fallback** — If the ratio didn't trigger but the team held
       a lead or deficit exceeding 800 gold/min at any point after
       minute 15, the game still qualifies as Throw (lost after big lead),
       Comeback (won despite big deficit), or Stomped (lost with big deficit).

    5. **Even** — Neither side dominated enough to qualify above.

    Returns:
        (match_type, peak_lead, peak_deficit) where lead/deficit are the
        maximum gold advantage / disadvantage from the player's perspective.
    """
    if detail is None or not detail.radiant_gold_adv:
        return ("-", None, None)

    team_adv = (
        detail.radiant_gold_adv
        if match.is_radiant
        else [-v for v in detail.radiant_gold_adv]
    )
    max_lead = max(team_adv)
    max_deficit = min(team_adv)

    pct_ahead, pct_behind, reversals, has_peak_lead, has_peak_deficit = (
        _curve_metrics(team_adv)
    )

    # Dominance ratio: how skewed is time-ahead vs time-behind
    if pct_ahead > 0 and pct_behind > 0:
        ratio = max(pct_ahead / pct_behind, pct_behind / pct_ahead)
        dominant_side = "ahead" if pct_ahead > pct_behind else "behind"
    elif pct_ahead > 0:
        ratio = 99.0
        dominant_side = "ahead"
    elif pct_behind > 0:
        ratio = 99.0
        dominant_side = "behind"
    else:
        ratio = 1.0
        dominant_side = "neither"

    dominance_threshold = 2.0

    # 1. Chaotic: many reversals override everything
    if reversals >= 3:
        match_type = "Chaotic"
    # 2-3. Ratio-based: stomp/stomped vs comeback/throw
    elif match.won:
        if ratio >= dominance_threshold and dominant_side == "ahead":
            match_type = "Stomp"
        elif ratio >= dominance_threshold and dominant_side == "behind":
            match_type = "Comeback"
        # 4. Peak fallback: won despite a massive deficit at some point
        elif has_peak_deficit:
            match_type = "Comeback"
        else:
            match_type = "Even"
    else:
        if ratio >= dominance_threshold and dominant_side == "behind":
            match_type = "Stomped"
        elif ratio >= dominance_threshold and dominant_side == "ahead":
            match_type = "Throw"
        # 4. Peak fallback: lost after holding a massive lead
        elif has_peak_lead:
            match_type = "Throw"
        elif has_peak_deficit:
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

    # Participation: from OpenDota teamfight_participation (0-1 float)
    if player.teamfight_participation > 0:
        contrib.fight = player.teamfight_participation * 100

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

    # Tower damage: tower_damage / team total
    team_tower_dmg = sum(p.tower_damage for p in teammates)
    if team_tower_dmg > 0:
        contrib.tower_damage = player.tower_damage / team_tower_dmg * 100

    # Damage taken: total_damage_taken / team total
    team_dmg_taken = sum(p.total_damage_taken for p in teammates)
    if team_dmg_taken > 0:
        contrib.damage_taken = player.total_damage_taken / team_dmg_taken * 100

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
        hero_damage=player.hero_damage,
        tower_damage=player.tower_damage,
        damage_taken=player.total_damage_taken,
        hero_healing=player.hero_healing,
        gpm=player.gold_per_min,
        xpm=player.xp_per_min,
        last_hits=player.last_hits,
        denies=player.denies,
        lh_at_10=lh_at_10,
        time_dead=player.life_state_dead,
        net_worth=player.net_worth,
        party_size=player.party_size,
        longest_kill_streak=player.longest_kill_streak,
        apm=player.actions_per_min,
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
