from datetime import datetime, timedelta, timezone

import discord

from dota.display.table import fmt_gold, fmt_pct, format_duration
from dota.models.match import ClassifiedMatch

AEST = timezone(timedelta(hours=10))


def format_date_discord(timestamp: int) -> str:
    """Format as 'Tuesday 25 May - 2:43AM'."""
    dt = datetime.fromtimestamp(timestamp, tz=AEST)
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%A')} {dt.day} {dt.strftime('%b')} - {hour}:{dt.minute:02d}{ampm}"


TYPE_EMOJI = {
    "Stomp": "\U0001f7e2",  # green circle
    "Stomped": "\U0001f534",  # red circle
    "Comeback": "\U0001f451",  # crown
    "Throw": "\U0001f7e0",  # orange circle
    "Chaotic": "\U0001f300",  # cyclone
    "Even": "\u26aa",  # white circle
    "-": "\u2796",  # minus
}


def _is_parsed(cm: ClassifiedMatch) -> bool:
    return cm.match_detail is not None and bool(cm.match_detail.radiant_gold_adv)


def _match_description(cm: ClassifiedMatch) -> str:
    """Return the text body for a summary match embed."""
    m = cm.match
    s = cm.stats
    result = "Win" if m.won else "Loss"
    type_icon = TYPE_EMOJI.get(cm.match_type, "")
    display_type = "Threw" if cm.match_type == "Throw" else cm.match_type

    party = f"Party: **{s.party_size}**" if s.party_size > 1 else "Solo"

    return (
        f"{format_date_discord(m.start_time)}\n"
        f"{result} - {display_type} {type_icon}\n"
        f"KDA: {m.kills}/{m.deaths}/{m.assists}  |  {party}\n"
        f"Length: {format_duration(m.duration)}\n"
        f"LH/DN: **{s.last_hits}/{s.denies}**\n"
        f"GPM: **{s.gpm}**  |  XPM: **{s.xpm}**\n"
        f"Lead: **{fmt_gold(cm.peak_lead)}**  |  Deficit: **{fmt_gold(cm.peak_deficit)}**\n"
        + "\u2500"
        * 30
    )


def build_summary_embeds(
    player_name: str,
    turbo_mmr: float | None,
    matches: list[ClassifiedMatch],
    hero_icons: dict[str, str] | None = None,
    avatar_url: str | None = None,
    weekly_wl: dict | None = None,
    weekly_seconds: int = 0,
    page: int = 0,
    total_pages: int = 1,
) -> list[discord.Embed]:
    title = f"{player_name}"
    if turbo_mmr is not None:
        title += f"  |  Turbo MMR: {turbo_mmr:.0f}"

    lines = []
    if weekly_wl:
        wins = weekly_wl.get("win", 0)
        losses = weekly_wl.get("lose", 0)
        total = wins + losses
        if total > 0:
            win_pct = wins / total * 100
            loss_pct = losses / total * 100
            lines.append(f"Games this week: **{total}**")
            lines.append(
                f"Wins: **{wins}** ({win_pct:.0f}%)  |  Losses: **{losses}** ({loss_pct:.0f}%)"
            )
    if weekly_seconds > 0:
        hours = weekly_seconds // 3600
        mins = (weekly_seconds % 3600) // 60
        lines.append(f"Game time: **{hours} hrs {mins} mins**")

    if lines:
        lines.append("\u2500" * 30)

    header = discord.Embed(
        title=title,
        description="\n".join(lines) if lines else None,
        color=discord.Color.blue(),
    )
    if avatar_url:
        header.set_thumbnail(url=avatar_url)
    embeds = [header]

    for i, cm in enumerate(matches, 1):
        color = discord.Color.green() if cm.match.won else discord.Color.red()
        embed = discord.Embed(
            title=f"{i}\ufe0f\u20e3  {cm.hero_name} ({cm.lane})",
            description=_match_description(cm),
            color=color,
        )
        if hero_icons:
            icon_url = hero_icons.get(str(cm.match.hero_id))
            if icon_url:
                embed.set_thumbnail(url=icon_url)
        embeds.append(embed)

    footer = "React with a number to see match details"
    if total_pages > 1:
        footer = f"Page {page + 1}/{total_pages} — {footer}"
    embeds[-1].set_footer(text=footer)
    return embeds


def build_detail_embed(
    cm: ClassifiedMatch,
    graph_filename: str | None = None,
) -> discord.Embed:
    m = cm.match
    s = cm.stats
    c = cm.contribution

    color = discord.Color.green() if m.won else discord.Color.red()
    type_icon = TYPE_EMOJI.get(cm.match_type, "")

    embed = discord.Embed(
        title=f"{cm.hero_name} ({'Radiant' if m.is_radiant else 'Dire'} - {cm.lane})",
        color=color,
    )
    if graph_filename:
        embed.set_image(url=f"attachment://{graph_filename}")

    embed.add_field(name="K/D/A", value=f"**{m.kills}/{m.deaths}/{m.assists}**")
    embed.add_field(name="GPM / XPM", value=f"{s.gpm} / {s.xpm}")
    embed.add_field(name="Net Worth", value=fmt_gold(s.net_worth))
    embed.add_field(name="LH/DN", value=f"{s.last_hits}/{s.denies}")
    embed.add_field(
        name="LH@10", value=str(s.lh_at_10) if s.lh_at_10 is not None else "-"
    )
    embed.add_field(name="Duration", value=format_duration(m.duration))
    display_type = "Threw" if cm.match_type == "Throw" else cm.match_type
    embed.add_field(name="Type", value=f"{type_icon} {display_type}")
    embed.add_field(name="Max Lead", value=fmt_gold(cm.peak_lead))
    embed.add_field(name="Max Deficit", value=fmt_gold(cm.peak_deficit))
    embed.add_field(name="Healing", value=fmt_gold(s.hero_healing))
    deaths_10_val = str(s.deaths_at_10) if s.deaths_at_10 is not None else "-"
    embed.add_field(name="Deaths@10", value=deaths_10_val)
    embed.add_field(name="Time Dead", value=format_duration(s.time_dead))
    embed.add_field(name="APM", value=str(s.apm) if s.apm > 0 else "-")
    streak_val = str(s.longest_kill_streak) if s.longest_kill_streak > 0 else "-"
    embed.add_field(name="Kill Streak", value=streak_val)

    embed.add_field(name="\u200b\nTeam Contribution", value="\u200b", inline=False)
    embed.add_field(
        name="Damage", value=f"{fmt_gold(s.hero_damage)}\n{fmt_pct(c.damage)}"
    )
    embed.add_field(
        name="Dmg Taken", value=f"{fmt_gold(s.damage_taken)}\n{fmt_pct(c.damage_taken)}"
    )
    embed.add_field(
        name="Tower Dmg", value=f"{fmt_gold(s.tower_damage)}\n{fmt_pct(c.tower_damage)}"
    )
    embed.add_field(name="Participation", value=fmt_pct(c.fight))
    embed.add_field(name="Vision", value=fmt_pct(c.vision))
    embed.add_field(name="Stuns", value=fmt_pct(c.stuns))
    embed.add_field(name="Lane Eff", value=fmt_pct(c.lane_eff))
    embed.add_field(name="\u200b", value="\u200b")
    if graph_filename:
        embed.add_field(name="\u200b\nGold / EXP Graph", value="\u200b", inline=False)
    embed.set_footer(
        text="\U0001f9e0 React to request AI analysis. Each request costs Kv money."
    )
    return embed


def _truncate(text: str, limit: int = 4096) -> str:
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_parse_embeds(
    matches: list,
    total_unparsed: int,
    heroes: dict[str, str],
    hero_icons: dict[str, str] | None = None,
) -> list[discord.Embed]:
    """Build card-style embeds for matches sent for parsing."""
    sending = len(matches)
    header = discord.Embed(
        title="Parse Requested",
        description=f"Sending **{sending}** of **{total_unparsed}** unparsed matches for parsing",
        color=discord.Color.orange(),
    )
    embeds = [header]

    for m in matches:
        hero_name = heroes.get(str(m.hero_id), "Unknown")
        result = "Win" if m.won else "Loss"
        embed = discord.Embed(
            title=hero_name,
            description=(
                f"{format_date_discord(m.start_time)}\n"
                f"{result}  |  KDA: {m.kills}/{m.deaths}/{m.assists}\n"
                f"Duration: {format_duration(m.duration)}\n"
                f"Match ID: `{m.match_id}`"
            ),
            color=discord.Color.orange(),
        )
        if hero_icons:
            icon_url = hero_icons.get(str(m.hero_id))
            if icon_url:
                embed.set_thumbnail(url=icon_url)
        embeds.append(embed)

    embeds[-1].set_footer(text="Please wait up to 5 minutes for parsing to complete")
    return embeds


def build_peers_embeds(
    player_name: str,
    peers: list[dict],
) -> list[discord.Embed]:
    """Build card-style embeds for the top peers."""
    header = discord.Embed(
        title=f"{player_name}'s Recent Peers (30 days)",
        description=f"Top **{len(peers)}** most played with",
        color=discord.Color.blue(),
    )
    embeds = [header]

    for i, peer in enumerate(peers, 1):
        name = peer.get("personaname") or "Unknown"
        games = peer.get("with_games", 0)
        wins = peer.get("with_win", 0)
        win_pct = (wins / games * 100) if games > 0 else 0
        avg_gpm = peer.get("with_gpm_sum", 0) // games if games > 0 else 0
        avg_xpm = peer.get("with_xpm_sum", 0) // games if games > 0 else 0

        embed = discord.Embed(
            title=f"{i}\ufe0f\u20e3  {name}",
            description=(
                f"Games: **{games}**  |  Win Rate: **{win_pct:.0f}%**\n"
                f"Avg GPM: **{avg_gpm}**  |  Avg XPM: **{avg_xpm}**"
            ),
            color=discord.Color.blue(),
        )
        avatar = peer.get("avatarfull")
        if avatar:
            embed.set_thumbnail(url=avatar)
        embeds.append(embed)

    embeds[-1].set_footer(text="React with a number to view their matches")
    return embeds


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
