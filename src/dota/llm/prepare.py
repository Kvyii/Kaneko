import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

_ITEM_FIELDS = [
    "item_0", "item_1", "item_2", "item_3", "item_4", "item_5",
]

# Components and consumables to filter out of purchase_log
_MINOR_ITEMS = {
    "tango", "clarity", "enchanted_mango", "faerie_fire", "ward_observer",
    "ward_sentry", "smoke_of_deceit", "dust", "gem", "tpscroll", "branches",
    "circlet", "mantle", "slippers", "gauntlets", "ring_of_protection",
    "quelling_blade", "stout_shield", "orb_of_venom", "blight_stone",
    "wind_lace", "ring_of_regen", "sobi_mask", "gloves", "boots_of_elves",
    "belt_of_strength", "robe", "cloak", "ring_of_health", "void_stone",
    "energy_booster", "vitality_booster", "point_booster", "ogre_axe",
    "blade_of_alacrity", "staff_of_wizardry", "fluffy_hat", "blades_of_attack",
    "chainmail", "helm_of_iron_will", "broadsword", "claymore", "javelin",
    "mithril_hammer", "platemail", "hyperstone", "ultimate_orb", "demon_edge",
    "mystic_staff", "reaver", "eaglesong", "sacred_relic", "recipe",
    "blood_grenade", "observers_ward", "sentry_ward",
    "flask", "boots", "magic_stick", "infused_raindrop",
}

_PLAYER_KEEP_FIELDS = {
    # Identity & skill
    "player_slot", "hero_id", "personaname", "account_id", "rank_tier",
    # Core stats
    "kills", "deaths", "assists", "level", "net_worth",
    "gold_per_min", "xp_per_min", "last_hits", "denies",
    "hero_damage", "tower_damage", "hero_healing", "gold_spent",
    # Items (will be mapped to names)
    "item_0", "item_1", "item_2", "item_3", "item_4", "item_5",
    # Role & lane
    "lane", "lane_role", "is_roaming", "lane_efficiency", "teamfight_participation",
    # Contribution
    "obs_placed", "sen_placed", "stuns",
    "kill_streaks", "multi_kills",
    # Damage breakdowns (will be filtered to hero-only)
    "damage", "damage_taken",
    # Timing
    "purchase_log", "gold_t", "lh_t", "xp_t",
    # Buffs
    "aghanims_scepter", "aghanims_shard", "moonshard",
}

_MATCH_KEEP_FIELDS = {
    "match_id", "radiant_gold_adv", "radiant_xp_adv",
    "duration", "radiant_win", "radiant_score", "dire_score",
    "game_mode", "first_blood_time",
}


def _load_heroes() -> dict[str, str]:
    with open(DATA_DIR / "heroes.json") as f:
        heroes = json.load(f)
    return {str(hero_id): data["localized_name"] for hero_id, data in heroes.items()}


def _load_rank_tiers() -> dict[str, str]:
    """Load rank tier medal names from data/rank_tiers.json."""
    with open(DATA_DIR / "rank_tiers.json") as f:
        return json.load(f)


def _map_rank_tier(rank_tier: int, tiers: dict[str, str]) -> str:
    """Map a rank_tier int (e.g. 45) to 'Archon 5'."""
    medal = str(rank_tier // 10)
    star = rank_tier % 10
    name = tiers.get(medal, "Unknown")
    if medal == "8":
        return name  # Immortal has no stars
    return f"{name} {star}" if star > 0 else name


def _load_game_modes() -> dict[int, str]:
    """Load game mode mappings from data/game_mode.json."""
    with open(DATA_DIR / "game_mode.json") as f:
        modes = json.load(f)
    return {
        int(k): v["name"].replace("game_mode_", "").replace("_", " ").title()
        for k, v in modes.items()
    }


def _load_items() -> tuple[dict[str, str], dict[str, str]]:
    """Load item mappings: (id -> dname, key -> dname)."""
    with open(DATA_DIR / "item_ids.json") as f:
        items = json.load(f)
    id_to_name = {
        str(data["id"]): data.get("dname", key)
        for key, data in items.items()
        if "id" in data
    }
    key_to_name = {
        key: data.get("dname", key)
        for key, data in items.items()
    }
    return id_to_name, key_to_name


def prepare_for_llm(raw: dict) -> dict:
    """Extract and enrich the fields relevant for LLM analysis from raw cache data."""
    heroes = _load_heroes()
    items_by_id, items_by_key = _load_items()
    rank_tiers = _load_rank_tiers()
    game_modes = _load_game_modes()

    # Match-level fields
    match_data = {k: v for k, v in raw.items() if k in _MATCH_KEEP_FIELDS}

    # Rename match-level fields to human-readable names
    _MATCH_RENAMES = {
        "radiant_gold_adv": "Gold Advantage to Radiant (per Minute)",
        "radiant_xp_adv": "XP Advantage to Radiant (per Minute)",
        "radiant_win": "Radiant Win",
        "radiant_score": "Radiant Kills",
        "dire_score": "Dire Kills",
        "first_blood_time": "First Blood Time (seconds)",
        "duration": "Duration (seconds)",
        "game_mode": "Game Mode",
        "match_id": "Match ID",
    }
    for old, new in _MATCH_RENAMES.items():
        if old in match_data:
            match_data[new] = match_data.pop(old)

    # Map game mode ID to human-readable name
    if "Game Mode" in match_data and isinstance(match_data["Game Mode"], int):
        match_data["Game Mode"] = game_modes.get(match_data["Game Mode"], str(match_data["Game Mode"]))

    # Split players into radiant/dire
    radiant = []
    dire = []
    for p in raw.get("players", []):
        prepared = _prepare_player(p, heroes, items_by_id, items_by_key, rank_tiers)
        slot = p.get("player_slot", 0)
        prepared.pop("player_slot", None)
        if slot < 128:
            radiant.append(prepared)
        else:
            dire.append(prepared)

    return {
        "match_data": match_data,
        "radiant": radiant,
        "dire": dire,
    }


def _round_floats(obj, decimals: int = 3):
    """Recursively round all floats in a nested structure to n decimal places."""
    if isinstance(obj, float):
        return round(obj, decimals)
    if isinstance(obj, dict):
        return {k: _round_floats(v, decimals) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(item, decimals) for item in obj]
    return obj


def _filter_hero_only(damage_dict: dict) -> dict:
    """Keep only hero-vs-hero damage entries."""
    return {
        k: v for k, v in damage_dict.items()
        if "npc_dota_hero_" in k
    }


def _filter_purchase_log(log: list[dict], items_by_key: dict[str, str]) -> list[dict]:
    """Keep only completed/major item purchases, mapping keys to display names."""
    filtered = []
    for entry in log:
        key = entry.get("key", "")
        if key in _MINOR_ITEMS or key.startswith("recipe"):
            continue
        filtered.append({
            "time": entry.get("time"),
            "key": items_by_key.get(key, key),
        })
    return filtered


def _map_lane(lane: int, is_radiant: bool) -> str:
    """Map OpenDota lane number to a role-based lane name.

    OpenDota lanes: 1=bot, 2=mid, 3=top.
    Radiant: bot=safelane, top=offlane.
    Dire: top=safelane, bot=offlane.
    """
    if lane == 2:
        return "Mid"
    if is_radiant:
        return "Safelane" if lane == 1 else "Offlane" if lane == 3 else "Unknown"
    else:
        return "Safelane" if lane == 3 else "Offlane" if lane == 1 else "Unknown"


def _prepare_player(
    player: dict, heroes: dict[str, str],
    items_by_id: dict[str, str], items_by_key: dict[str, str],
    rank_tiers: dict[str, str],
) -> dict:
    """Select relevant player fields and map IDs to names."""
    result = {k: v for k, v in player.items() if k in _PLAYER_KEEP_FIELDS}

    # Map rank_tier to readable medal name
    if "rank_tier" in result and isinstance(result["rank_tier"], int):
        result["rank_tier"] = _map_rank_tier(result["rank_tier"], rank_tiers)

    # Map lane number to human-readable name based on team
    is_radiant = player.get("player_slot", 0) < 128
    if "lane" in result and isinstance(result["lane"], int):
        result["lane"] = _map_lane(result["lane"], is_radiant)

    # Condense gold_t, lh_t, xp_t into 5-min interval snapshots
    gold_t = result.pop("gold_t", None)
    lh_t = result.pop("lh_t", None)
    xp_t = result.pop("xp_t", None)
    if gold_t and lh_t and xp_t:
        progression = {}
        for i in range(0, len(gold_t), 5):
            minute = i  # each index = 1 minute
            progression[f"{minute}min"] = {
                "gold": gold_t[i],
                "last_hits": lh_t[i],
                "xp": xp_t[i],
            }
        result["progression_per_5min"] = progression

    # Map hero_id to hero_name, then drop the raw ID
    hero_id = str(result.get("hero_id", ""))
    if hero_id in heroes:
        result["hero_name"] = heroes[hero_id]
    result.pop("hero_id", None)

    # Map item IDs to item names, collect into a list
    items = []
    for field in _ITEM_FIELDS:
        item_id = result.pop(field, None)
        if item_id is not None and item_id != 0:
            items.append(items_by_id.get(str(item_id), f"unknown_{item_id}"))
    if items:
        result["Items"] = items

    # Filter damage dicts to hero-only
    if "damage" in result and isinstance(result["damage"], dict):
        result["damage"] = _filter_hero_only(result["damage"])
    if "damage_taken" in result and isinstance(result["damage_taken"], dict):
        result["damage_taken"] = _filter_hero_only(result["damage_taken"])

    # Filter purchase_log to major items only, map keys to display names
    if "purchase_log" in result and isinstance(result["purchase_log"], list):
        result["purchase_log"] = _filter_purchase_log(result["purchase_log"], items_by_key)

    # Convert teamfight_participation from decimal to percentage
    if "teamfight_participation" in result and isinstance(result["teamfight_participation"], (int, float)):
        result["teamfight_participation"] = round(result["teamfight_participation"] * 100, 1)

    # Rename fields to human-readable names
    _PLAYER_RENAMES = {
        "hero_name": "Hero",
        "personaname": "Player Name",
        "account_id": "Account ID",
        "rank_tier": "Rank Tier",
        "computed_mmr": "Estimated MMR",
        "kills": "Kills",
        "deaths": "Deaths",
        "assists": "Assists",
        "level": "Level",
        "net_worth": "Net Worth",
        "gold_per_min": "GPM",
        "xp_per_min": "XPM",
        "last_hits": "Last Hits",
        "denies": "Denies",
        "hero_damage": "Hero Damage",
        "tower_damage": "Tower Damage",
        "hero_healing": "Hero Healing",
        "gold_spent": "Gold Spent",
        "lane": "Lane",
        "lane_role": "Lane Role",
        "is_roaming": "Roaming",
        "lane_efficiency": "Lane Efficiency",
        "teamfight_participation": "Teamfight Participation (%)",
        "obs_placed": "Observer Wards Placed",
        "sen_placed": "Sentry Wards Placed",
        "stuns": "Stuns (seconds)",
        "kill_streaks": "Kill Streaks",
        "multi_kills": "Multi Kills",
        "damage": "Damage Dealt (hero only)",
        "damage_taken": "Damage Taken (hero only)",
        "purchase_log": "Item Purchase Log",
        "progression_per_5min": "Progression (per 5 min)",
        "aghanims_scepter": "Aghanim's Scepter",
        "aghanims_shard": "Aghanim's Shard",
        "moonshard": "Moon Shard",
    }
    for old, new in _PLAYER_RENAMES.items():
        if old in result:
            result[new] = result.pop(old)

    # Round all floats to 3 decimal places
    result = _round_floats(result)

    return result


# Keep the old function name as an alias for backwards compat
enrich_match_data = prepare_for_llm
