import json
from pathlib import Path

from rich.console import Console

from dota.api.client import OpenDotaClient
from dota.analysis.classifier import build_classified_matches
from dota.cache import MatchCache
from dota.config import load_config
from dota.display.table import display_matches

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_heroes() -> dict[str, str]:
    with open(DATA_DIR / "heroes.json") as f:
        heroes = json.load(f)
    return {
        str(hero_id): data["localized_name"]
        for hero_id, data in heroes.items()
    }


def main() -> None:
    console = Console()
    config = load_config()
    cache = MatchCache()
    client = OpenDotaClient()

    try:
        player = client.fetch_player(config.player_id)
        name = player.get("profile", {}).get("personaname", "Unknown")
        turbo_mmr = player.get("computed_mmr_turbo")

        console.print(f"\n[bold]Player:[/bold] {name}")
        if turbo_mmr is not None:
            console.print(f"[bold]Turbo MMR:[/bold] {turbo_mmr:.0f}")

        console.print("\nFetching recent matches...")
        matches = client.fetch_recent_matches(config.player_id, limit=5)

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
        display_matches(classified, console)
    finally:
        client.close()


if __name__ == "__main__":
    main()
