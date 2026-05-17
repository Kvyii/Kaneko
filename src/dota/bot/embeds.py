from datetime import datetime, timezone, timedelta

import discord

from dota.display.table import fmt_gold, fmt_pct, format_duration
from dota.models.match import ClassifiedMatch

AEST = timezone(timedelta(hours=10))


def _format_date_discord(timestamp: int) -> str:
    """Format as 'Tuesday 25 May - 2:43AM'."""
    dt = datetime.fromtimestamp(timestamp, tz=AEST)
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%A')} {dt.day} {dt.strftime('%b')} - {hour}:{dt.minute:02d}{ampm}"

TYPE_EMOJI = {
    "Stomp": "\U0001f7e2",    # green circle
    "Stomped": "\U0001f534",   # red circle
    "Comeback": "\U0001f4a0",  # diamond with dot
    "Throw": "\U0001f7e1",     # yellow circle
    "Even": "\u26aa",          # white circle
    "-": "\u2796",             # minus
}


def _is_parsed(cm: ClassifiedMatch) -> bool:
    return cm.match_detail is not None and bool(cm.match_detail.radiant_gold_adv)


def _match_field(i: int, cm: ClassifiedMatch) -> tuple[str, str]:
    """Return (name, value) for a summary embed field."""
    m = cm.match
    s = cm.stats
    result = "\u2705 Win" if m.won else "\u274c Loss"
    type_icon = TYPE_EMOJI.get(cm.match_type, "")

    name = f"{i}\ufe0f\u20e3  {cm.hero_name} ({cm.lane})"
    value = (
        f"{result}  |  {m.kills}/{m.deaths}/{m.assists}  |  {format_duration(m.duration)}\n"
        f"{type_icon} {cm.match_type}\n"
        f"{_format_date_discord(m.start_time)}\n"
        f"GPM: **{s.gpm}**  |  XPM: **{s.xpm}**  |  LH/DN: **{s.last_hits}/{s.denies}**\n"
        f"Lead: **{fmt_gold(cm.peak_lead)}**  |  Deficit: **{fmt_gold(cm.peak_deficit)}**"
    )
    return name, value


def build_summary_embed(
    player_name: str,
    turbo_mmr: float | None,
    matches: list[ClassifiedMatch],
) -> discord.Embed:
    title = f"{player_name}"
    if turbo_mmr is not None:
        title += f"  |  Turbo MMR: {turbo_mmr:.0f}"

    embed = discord.Embed(title=title, color=discord.Color.blue())

    for i, cm in enumerate(matches, 1):
        name, value = _match_field(i, cm)
        embed.add_field(name=name, value=value, inline=False)

    embed.set_footer(text="React with a number to see match details")
    return embed


def build_detail_embed(cm: ClassifiedMatch) -> discord.Embed:
    m = cm.match
    s = cm.stats
    c = cm.contribution

    color = discord.Color.green() if m.won else discord.Color.red()
    result = "\u2705 Win" if m.won else "\u274c Loss"
    type_icon = TYPE_EMOJI.get(cm.match_type, "")

    embed = discord.Embed(
        title=f"{cm.hero_name} ({cm.lane})  \u2014  {result}",
        color=color,
    )

    embed.add_field(name="K/D/A", value=f"**{m.kills}/{m.deaths}/{m.assists}**")
    embed.add_field(name="GPM / XPM", value=f"{s.gpm} / {s.xpm}")
    embed.add_field(name="LH/DN", value=f"{s.last_hits}/{s.denies}")
    embed.add_field(name="LH@10", value=str(s.lh_at_10) if s.lh_at_10 is not None else "-")
    embed.add_field(name="Duration", value=format_duration(m.duration))
    embed.add_field(name="Type", value=f"{type_icon} {cm.match_type}")
    embed.add_field(name="Max Lead", value=fmt_gold(cm.peak_lead))
    embed.add_field(name="Max Deficit", value=fmt_gold(cm.peak_deficit))
    embed.add_field(name="Tower Dmg", value=fmt_gold(s.tower_damage))
    embed.add_field(name="Healing", value=fmt_gold(s.hero_healing))
    embed.add_field(name="Time Dead", value=format_duration(s.time_dead))
    embed.add_field(name="\u200b", value="\u200b")

    embed.add_field(name="\u200b\nTeam Contribution", value="\u200b", inline=False)
    embed.add_field(name="Fight", value=fmt_pct(c.fight))
    embed.add_field(name="Damage", value=fmt_pct(c.damage))
    embed.add_field(name="Vision", value=fmt_pct(c.vision))
    embed.add_field(name="Stuns", value=fmt_pct(c.stuns))
    embed.add_field(name="Lane Eff", value=fmt_pct(c.lane_eff))
    embed.add_field(name="\u200b", value="\u200b")
    embed.set_footer(text="\U0001f9e0 React to request AI analysis")
    return embed


def _truncate(text: str, limit: int = 4096) -> str:
    if len(text) > limit:
        return text[:limit - 3] + "..."
    return text


def build_analysis_embeds(sections: dict[str, str]) -> list[discord.Embed]:
    """Build up to 3 embeds from the structured LLM response."""
    embeds = []

    titles = {
        "match_summary": "\U0001f4ca Match Summary",
        "player_performance": "\U0001f3af Player Performance",
        "core_reasons": "\U0001f3c6 Core Reasons",
    }
    colors = {
        "match_summary": discord.Color.blue(),
        "player_performance": discord.Color.purple(),
        "core_reasons": discord.Color.gold(),
    }

    for key in ("match_summary", "player_performance", "core_reasons"):
        text = sections.get(key, "")
        if not text:
            continue
        embed = discord.Embed(
            title=titles[key],
            description=_truncate(text),
            color=colors[key],
        )
        embeds.append(embed)

    return embeds
