import json
from pathlib import Path

import httpx
from dotenv import load_dotenv
from rich.console import Console

from dota.api.client import OpenDotaClient
from dota.analysis.classifier import build_classified_matches
from dota.cache import MatchCache
from dota.config import load_config
from dota.display.table import display_matches
from dota.llm.client import analyze_match
from dota.llm.prepare import enrich_match_data
from dota.prompts.match_analysis import build_system_prompt

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_heroes() -> dict[str, str]:
    with open(DATA_DIR / "heroes.json") as f:
        heroes = json.load(f)
    return {
        str(hero_id): data["localized_name"]
        for hero_id, data in heroes.items()
    }


def main() -> None:
    load_dotenv()
    console = Console()
    config = load_config()
    cache = MatchCache()
    client = OpenDotaClient()

    try:
        try:
            player = client.fetch_player(config.player_id)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            console.print(f"[red]Failed to reach OpenDota API: {e}[/red]")
            return

        name = player.get("profile", {}).get("personaname", "Unknown")
        turbo_mmr = player.get("computed_mmr_turbo")

        console.print(f"\n[bold]Player:[/bold] {name}")
        if turbo_mmr is not None:
            console.print(f"[bold]Turbo MMR:[/bold] {turbo_mmr:.0f}")

        console.print("\nFetching recent matches...")
        try:
            matches = client.fetch_recent_matches(config.player_id, limit=5)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            console.print(f"[red]Failed to fetch matches: {e}[/red]")
            return

        if not matches:
            console.print("[yellow]No matches found.[/yellow]")
            return

        match_ids = [m.match_id for m in matches]
        console.print("Fetching match details...")
        details = client.fetch_match_details(match_ids, cache=cache)

        # Request parsing for unparsed matches
        unparsed = [
            mid for mid in match_ids
            if mid not in details or not details[mid].radiant_gold_adv
        ]
        if unparsed:
            console.print(
                f"[yellow]Requesting parse for {len(unparsed)} unparsed match(es)...[/yellow]"
            )
            requested = client.request_parse(unparsed)
            if requested:
                console.print(
                    f"[yellow]Queued {len(requested)} match(es) for parsing. "
                    f"Run again later for full stats.[/yellow]"
                )

        heroes = load_heroes()
        classified = build_classified_matches(matches, details, heroes)

        def do_analyze(match_id: int) -> str:
            raw = cache.get_raw(match_id)
            if raw:
                match_json = enrich_match_data(raw)
            else:
                detail = details.get(match_id)
                match_json = detail.model_dump() if detail else {}

            # Find the requesting player in the prepared data
            player_slot = None
            for m in matches:
                if m.match_id == match_id:
                    player_slot = m.player_slot
                    break

            team = "Radiant" if player_slot is not None and player_slot < 128 else "Dire"
            team_key = "radiant" if team == "Radiant" else "dire"

            # Find player data in the enriched match json
            player_data = {}
            if isinstance(match_json.get(team_key), list):
                for p in match_json[team_key]:
                    if p.get("Account ID") == config.player_id:
                        player_data = p
                        break

            prompt = build_system_prompt(player_data, team, match_json)
            return analyze_match(prompt)

        display_matches(classified, console, analyze_fn=do_analyze)
    finally:
        client.close()


if __name__ == "__main__":
    main()
