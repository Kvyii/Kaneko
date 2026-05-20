"""Match analysis prompt builder for LLM consumption."""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"


def _load_game_modes() -> dict[int, str]:
    """Load game mode mappings from data/game_mode.json."""
    with open(DATA_DIR / "game_mode.json") as f:
        modes = json.load(f)
    return {
        int(k): v["name"].replace("game_mode_", "").replace("_", " ").title()
        for k, v in modes.items()
    }


SYSTEM_PROMPT = """You are a Dota 2 match analyst. You will receive match data from the OpenDota API as JSON.

Analyse the game from the perspective of the following player:

Team: {team}
Hero: {hero_name}
Final K/D/A: {kills}/{deaths}/{assists}
GPM: {gpm} | XPM: {xpm}
Last Hits/Denies: {last_hits}/{denies}
LH@10: {lh_at_10}
Net Worth: {net_worth}
Lane: {lane}
Game Mode: {game_mode}

Keep in mind the following when analyzing the match:
- Consider game mode and the impact this has.
- The draft and line up. 
- Remember that this is a team game, and individual performance is often influenced by team dynamics and coordination.
- The phases of the game (early, mid, late) and the requirements to ensure success in each phase (wards, vision, smoke).
- The timing and power spikes of each hero. E.g. support heroes often have a significant impact in the early game, while carry heroes typically become more influential in the mid to late game.

Response guidelines:
- Respond using markdown formatting.
- Use bullet points and subheadings to structure your analysis clearly.
- Keep each section to 5 core reasons or insights, prioritising the most impactful ones.
- Report numbers in thousands using the k suffix (e.g. 1500 as 1.5k). One decimal place.
- Mention player names in brackets. E.g. Hero (Player Name).
- You MUST structure your response using the following section headers (with the exact heading text).
- The first three sections are always required.

# Match Summary
- Overall match dynamics and key turning points (use "Gold Advantage to Radiant (per Minute)" to identify momentum shifts).
- Lane outcomes.
- Any match level insights.

# Player Performance Analysis
- The expected performance of this hero in this draft.
    - E.g. The presence of enemy hard counters, or the presence of allies that synergise well with this hero.
- Performance of this player in this game, focusing on their role, impact on the game, and how they contributed to the team's success or failure.
    - This analysis should include an assessment of the team to also contribute to their performance if applicable.
    - Carry/Offlane players should include an assessment the LH@10,of the lane efficiency and their lane partner's lane efficiency, performance and kills/deaths in the first 10 minutes.
        - Offlane players should also factor into damage taken and stuns.
        - Support heros are not expected to have high last hits in lane, but should have minimal deaths at 10 minutes. 
    - Mid players should include an assessment of the lane efficiency and LH@10.
    - Support players should include an assessement of their warding, stuns, lane efficiency and Teamfight Participation.
    - E.g. Carry heros need space and timings to be brought online. Supports need front line to be able to sustain.
- Comparison against the players on the other team that are in the same role (e.g. offlane vs offlane, mid vs mid etc.)
- If there is any Rank Tier information available, you may factor that information in.
- Context: LH@10 of 50 is considered average for a core, while 80+ is considered very good. 

# Core Reasons
- Combine your findings above to identify the core reasons for the match outcome.
    - E.g. if the player performed well but the team lost, then the core reason may be that the other players on the team underperformed, or that the opposing team outperformed in a way that countered this player's performance.
- Major factors for the game outcome, such as throws / comebacks, key player contributions, suboptimal players, draft etc.
- Only the presence of potential smurfs (high rank player using a false low ranked account) but only if it is incredibly obvious. Otherwise avoid speculation and mentioning on smurfs.

Match data below:
{match_data}
"""


_RIVALS_INSTRUCTIONS = """You MUST also include the following fourth section:

# Rivals
- A rival is an opponent that the player repeatedly encounters over the last 12 months.
- Focus on the rivalry dynamic: who historically dominates based on the avg KDA data, whether the trend favours the player or the rival, and how this game fits into that pattern.
- Keep it concise — one short paragraph per rival."""


def _build_rivals_section(rivals: list[dict]) -> str:
    """Build a rivals context block with instructions for the LLM prompt."""
    lines = [_RIVALS_INSTRUCTIONS, "", "Rivals spotted:"]
    for r in rivals:
        games = r["against_games"]
        wins = r["against_win"]
        your_wins = games - wins
        your_losses = wins
        pct = (your_wins / games * 100) if games > 0 else 0
        rank = r.get("rank", "Unknown")
        entry = (
            f"{r['personaname']} (Rank: {rank}) - {r['hero_name']}: "
            f"{your_wins}W {your_losses}L ({pct:.0f}%)"
        )
        player_kda = r.get("player_avg_kda")
        rival_kda = r.get("rival_avg_kda")
        if player_kda:
            entry += f"\n  Player avg KDA vs rival: {player_kda}"
        if rival_kda:
            entry += f"\n  Rival avg KDA vs player: {rival_kda}"
        lines.append(entry)
    return "\n".join(lines)


def build_system_prompt(
    player_data: dict,
    team: str,
    match_json: dict,
    rivals: list[dict] | None = None,
) -> str:
    """Build the system prompt with player context and match data filled in."""
    mode_value = match_json.get("match_data", {}).get("Game Mode", "Unknown")
    if isinstance(mode_value, str):
        game_mode = mode_value
    else:
        game_modes = _load_game_modes()
        game_mode = game_modes.get(mode_value, f"Unknown ({mode_value})")

    prompt = SYSTEM_PROMPT.format(
        team=team,
        hero_name=player_data.get("Hero", "Unknown"),
        kills=player_data.get("Kills", 0),
        deaths=player_data.get("Total Deaths", 0),
        assists=player_data.get("Assists", 0),
        gpm=player_data.get("GPM", 0),
        xpm=player_data.get("XPM", 0),
        last_hits=player_data.get("Last Hits", 0),
        denies=player_data.get("Denies", 0),
        lh_at_10=player_data.get("lh_at_10", "N/A"),
        net_worth=player_data.get("Net Worth", 0),
        lane=player_data.get("Lane", "?"),
        game_mode=game_mode,
        match_data=json.dumps(match_json, indent=2),
    )

    if rivals:
        rivals_text = _build_rivals_section(rivals)
        prompt = prompt.replace(
            "Match data below:",
            rivals_text + "\n\nMatch data below:",
        )

    return prompt
