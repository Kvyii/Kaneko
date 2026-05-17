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


def display_summary(matches: list[ClassifiedMatch], console: Console) -> None:
    """Display the main summary table (up to Max Def)."""
    table = Table(title="Recent Matches")

    table.add_column("#", justify="right", style="dim")
    table.add_column("Result", justify="center")
    table.add_column("Hero")
    table.add_column("K/D/A", justify="center")
    table.add_column("GPM", justify="right")
    table.add_column("XPM", justify="right")
    table.add_column("LH/DN", justify="center")
    table.add_column("LH@10", justify="right")
    table.add_column("Duration", justify="center")
    table.add_column("Date", justify="center")
    table.add_column("Type", justify="center")
    table.add_column("Max Lead", justify="right")
    table.add_column("Max Def", justify="right")

    for i, cm in enumerate(matches, 1):
        m = cm.match
        s = cm.stats
        kda = f"{m.kills}/{m.deaths}/{m.assists}"
        hero_display = f"{cm.hero_name} ({cm.lane})"
        lh_dn = f"{s.last_hits}/{s.denies}"

        table.add_row(
            str(i),
            "[green]Win[/green]" if m.won else "[red]Loss[/red]",
            hero_display,
            kda,
            str(s.gpm),
            str(s.xpm),
            lh_dn,
            str(s.lh_at_10) if s.lh_at_10 is not None else "-",
            format_duration(m.duration),
            format_date(m.start_time),
            TYPE_STYLES.get(cm.match_type, cm.match_type),
            fmt_gold(cm.peak_lead),
            fmt_gold(cm.peak_deficit),
        )

    console.print()
    console.print(table)


def display_detail(cm: ClassifiedMatch, console: Console) -> None:
    """Display detailed stats for a single match."""
    m = cm.match
    s = cm.stats
    c = cm.contribution

    table = Table(title=f"Match Detail — {cm.hero_name} ({cm.lane})")

    table.add_column("Result", justify="center")
    table.add_column("K/D/A", justify="center")
    table.add_column("GPM", justify="right")
    table.add_column("XPM", justify="right")
    table.add_column("LH/DN", justify="center")
    table.add_column("LH@10", justify="right")
    table.add_column("Duration", justify="center")
    table.add_column("Type", justify="center")
    table.add_column("Max Lead", justify="right")
    table.add_column("Max Def", justify="right")
    table.add_column("Twr Dmg", justify="right")
    table.add_column("Healing", justify="right")
    table.add_column("Dead", justify="right")
    table.add_column("Fight", justify="right")
    table.add_column("Dmg", justify="right")
    table.add_column("Vision", justify="right")
    table.add_column("Stuns", justify="right")
    table.add_column("Lane Eff", justify="right")

    table.add_row(
        "[green]Win[/green]" if m.won else "[red]Loss[/red]",
        f"{m.kills}/{m.deaths}/{m.assists}",
        str(s.gpm),
        str(s.xpm),
        f"{s.last_hits}/{s.denies}",
        str(s.lh_at_10) if s.lh_at_10 is not None else "-",
        format_duration(m.duration),
        TYPE_STYLES.get(cm.match_type, cm.match_type),
        fmt_gold(cm.peak_lead),
        fmt_gold(cm.peak_deficit),
        fmt_gold(s.tower_damage),
        fmt_gold(s.hero_healing),
        format_duration(s.time_dead),
        fmt_pct(c.fight),
        fmt_pct(c.damage),
        fmt_pct(c.vision),
        fmt_pct(c.stuns),
        fmt_pct(c.lane_eff),
    )

    console.print()
    console.print(table)


def prompt_detail(matches: list[ClassifiedMatch], console: Console) -> None:
    """Prompt user to select a match for detailed view."""
    count = len(matches)
    console.print()
    console.print("[bold]See advanced details?[/bold]")
    for i in range(1, count + 1):
        cm = matches[i - 1]
        console.print(f"  {i}. {cm.hero_name} ({cm.lane})")
    console.print(f"  {count + 1}. No")

    while True:
        choice = console.input(f"\nSelect [1-{count + 1}]: ").strip()
        if choice == str(count + 1):
            return
        if choice.isdigit() and 1 <= int(choice) <= count:
            display_detail(matches[int(choice) - 1], console)
            return
        console.print(f"[red]Please enter a number between 1 and {count + 1}[/red]")


def display_matches(matches: list[ClassifiedMatch], console: Console) -> None:
    """Display summary then offer detailed view."""
    display_summary(matches, console)
    prompt_detail(matches, console)
