from datetime import datetime, timezone, timedelta

from rich.console import Console
from rich.table import Table

from dota.models.match import ClassifiedMatch

AEST = timezone(timedelta(hours=10))


def fmt_gold(val: int | None) -> str:
    if val is None:
        return "-"
    return f"{val / 1000:.1f}k"


def fmt_pct(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:.0f}%"


def format_duration(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def format_date(timestamp: int) -> str:
    dt = datetime.fromtimestamp(timestamp, tz=AEST)
    hour = dt.hour % 12 or 12
    ampm = "am" if dt.hour < 12 else "pm"
    return f"{hour}:{dt.minute:02d}{ampm} {dt.strftime('%d %b %Y')}"


TYPE_STYLES = {
    "Stomp": "[green]Stomp[/green]",
    "Stomped": "[red]Stomped[/red]",
    "Comeback": "[cyan]Comeback[/cyan]",
    "Throw": "[yellow]Throw[/yellow]",
    "Even": "Even",
    "-": "-",
}


def display_matches(matches: list[ClassifiedMatch], console: Console) -> None:
    table = Table(title="Recent Matches")

    table.add_column("#", justify="right", style="dim")
    table.add_column("Result", justify="center")
    table.add_column("Hero")
    table.add_column("K/D/A", justify="center")
    table.add_column("Duration", justify="center")
    table.add_column("Date", justify="center")
    table.add_column("Type", justify="center")
    table.add_column("Max Lead", justify="right")
    table.add_column("Max Def", justify="right")
    table.add_column("Fight", justify="right")
    table.add_column("Dmg", justify="right")
    table.add_column("Vision", justify="right")
    table.add_column("Stuns", justify="right")
    table.add_column("Lane Eff", justify="right")

    for i, cm in enumerate(matches, 1):
        m = cm.match
        result = "[green]Win[/green]" if m.won else "[red]Loss[/red]"
        kda = f"{m.kills}/{m.deaths}/{m.assists}"
        hero_display = f"{cm.hero_name} ({cm.lane})"
        c = cm.contribution

        table.add_row(
            str(i),
            result,
            hero_display,
            kda,
            format_duration(m.duration),
            format_date(m.start_time),
            TYPE_STYLES.get(cm.match_type, cm.match_type),
            fmt_gold(cm.peak_lead),
            fmt_gold(cm.peak_deficit),
            fmt_pct(c.fight),
            fmt_pct(c.damage),
            fmt_pct(c.vision),
            fmt_pct(c.stuns),
            fmt_pct(c.lane_eff),
        )

    console.print()
    console.print(table)
