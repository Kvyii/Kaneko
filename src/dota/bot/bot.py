import asyncio
import json
import logging
import os
import time
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from dota.analysis.classifier import build_classified_matches
from dota.api.client import OpenDotaClient
from dota.bot.embeds import (
    build_analysis_embeds,
    build_detail_embed,
    build_parse_embeds,
    build_summary_embeds,
    format_date_discord,
)
from dota.bot.players import PlayerRegistry
from dota.display.graph import generate_advantage_graph
from dota.bot.usage import UsageTracker
from dota.cache import MatchCache
from dota.llm.client import analyze_match
from dota.llm.prepare import enrich_match_data
from dota.prompts.match_analysis import build_system_prompt

log = logging.getLogger("dota.bot")

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

NUMBER_EMOJIS = [
    "1\ufe0f\u20e3",
    "2\ufe0f\u20e3",
    "3\ufe0f\u20e3",
    "4\ufe0f\u20e3",
    "5\ufe0f\u20e3",
]
BRAIN_EMOJI = "\U0001f9e0"
LEFT_ARROW = "\u25c0"
RIGHT_ARROW = "\u25b6"
REACTION_TIMEOUT = 25.0  # seconds
PAGE_SIZE = 5
MAX_MATCHES = 20
OWNER_DISCORD_ID = 227439391147032576


STEAM_CDN = "https://cdn.cloudflare.steamstatic.com"


_HTTP_ERRORS: dict[int, str] = {
    400: "bad request",
    401: "unauthorized",
    403: "forbidden",
    404: "player or resource not found",
    429: "rate limited by OpenDota — try again later",
    500: "OpenDota internal server error",
    502: "OpenDota bad gateway",
    503: "OpenDota is temporarily unavailable",
    504: "OpenDota gateway timeout",
    521: "OpenDota server is down (Cloudflare 521)",
    522: "OpenDota connection timed out (Cloudflare 522)",
    524: "OpenDota request timed out (Cloudflare 524)",
}


def _api_error_msg(exc: Exception) -> str:
    """Return a user-friendly message from an API exception."""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return _HTTP_ERRORS.get(code, f"HTTP {code}")
    if isinstance(exc, httpx.TimeoutException):
        return "request timed out"
    if isinstance(exc, httpx.ConnectError):
        return "could not connect to OpenDota"
    return str(exc)


def _load_heroes() -> dict[str, str]:
    with open(DATA_DIR / "heroes.json") as f:
        heroes = json.load(f)
    return {str(hero_id): data["localized_name"] for hero_id, data in heroes.items()}


def _load_hero_icons() -> dict[str, str]:
    with open(DATA_DIR / "heroes.json") as f:
        heroes = json.load(f)
    return {
        str(hero_id): f"{STEAM_CDN}{data['img']}"
        for hero_id, data in heroes.items()
        if data.get("img")
    }


class DotaBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.reactions = True
        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self)
        self.registry = PlayerRegistry()
        self.cache = MatchCache()
        self.client = OpenDotaClient()
        self.heroes = _load_heroes()
        self.hero_icons = _load_hero_icons()

        self.usage = UsageTracker()

        # Active session lock: only one /matches at a time
        self._active_session: int | None = (
            None  # discord user id of active session owner
        )

    async def setup_hook(self) -> None:
        self.tree.add_command(_register)
        self.tree.add_command(_matches)
        self.tree.add_command(_usage)
        self.tree.add_command(_parse)
        self.tree.add_command(_info)
        # Sync to specific guilds for instant command updates
        guild_env = os.environ.get("DISCORD_GUILD_IDS", "")
        guild_ids = [int(g) for g in guild_env.split(",") if g.strip()]
        if guild_ids:
            for guild_id in guild_ids:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Synced commands to guild %d", guild_id)
        else:
            await self.tree.sync()
            log.info("Synced commands globally")

    async def on_ready(self) -> None:
        log.info("Logged in as %s (ID: %s)", self.user, self.user.id)


bot = DotaBot()


@app_commands.command(name="register", description="Link your OpenDota player ID")
@app_commands.describe(player_id="Your OpenDota numeric player ID")
async def _register(interaction: discord.Interaction, player_id: int) -> None:
    log.info(
        "/register by %s (%s) — player_id=%d",
        interaction.user,
        interaction.user.id,
        player_id,
    )

    if bot.registry.is_banned(interaction.user.id):
        await interaction.response.send_message("You have been banned.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        player = await bot.client.fetch_player_async(player_id)
    except Exception:
        log.warning("/register failed — player_id=%d not found on OpenDota", player_id)
        await interaction.followup.send("Could not find that player ID on OpenDota.")
        return

    name = player.get("profile", {}).get("personaname", "Unknown")
    bot.registry.register(interaction.user.id, player_id)
    bot.usage.record_command(interaction.user.id, "register")
    log.info(
        "/register success — %s (%s) linked to %s (player_id=%d)",
        interaction.user,
        interaction.user.id,
        name,
        player_id,
    )

    embed = discord.Embed(
        title="Registered",
        description=f"Linked to **{name}** (ID: {player_id})",
        color=discord.Color.green(),
    )
    await interaction.followup.send(embed=embed)


@app_commands.command(name="usage", description="Show your bot usage stats")
async def _usage(interaction: discord.Interaction) -> None:
    user_id = interaction.user.id
    log.info("/usage by %s (%s)", interaction.user, user_id)

    if bot.registry.is_banned(user_id):
        await interaction.response.send_message("You have been banned.", ephemeral=True)
        return

    bot.usage.record_command(user_id, "usage")

    stats = bot.usage.get_usage(user_id)
    max_info, max_llm, max_parse = bot.registry.get_limits(user_id)

    # Lifetime command usage
    cmds = stats["commands"]
    cmd_lines = []
    for name, count in sorted(cmds.items()):
        cmd_lines.append(f"/{name}: **{count}**")
    cmd_text = "\n".join(cmd_lines) if cmd_lines else "None"

    # Remaining calls this hour
    info_remaining = max(0, max_info - stats["info_this_hour"])
    llm_remaining = max(0, max_llm - stats["llm_this_hour"])
    parse_remaining = max(0, max_parse - stats["parse_this_hour"])
    secs = stats["seconds_until_refresh"]
    mins = secs // 60
    secs = secs % 60

    embed = discord.Embed(
        title=f"Usage — {interaction.user.display_name}",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Lifetime Commands",
        value=cmd_text,
        inline=False,
    )
    embed.add_field(
        name="Total Usage",
        value=(
            f"API Calls: **{stats['api_calls']}**\n"
            f"AI analysis: **{stats['llm_calls']}**"
        ),
        inline=False,
    )
    embed.add_field(
        name="Remaining This Hour",
        value=(
            f"/matches: **{info_remaining}** / {max_info}\n"
            f"/parse: **{parse_remaining}** / {max_parse}\n"
            f"AI analysis: **{llm_remaining}** / {max_llm}\n"
            f"Refresh in **{mins}m {secs}s**"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="matches", description="Show your recent Dota 2 matches")
async def _matches(interaction: discord.Interaction) -> None:
    user_id = interaction.user.id
    log.info("/matches by %s (%s)", interaction.user, user_id)

    # Guard: banned
    if bot.registry.is_banned(user_id):
        await interaction.response.send_message("You have been banned.", ephemeral=True)
        return

    # Guard: registration
    player_id = bot.registry.get(user_id)
    if player_id is None:
        log.info("/matches rejected — %s (%s) not registered", interaction.user, user_id)
        await interaction.response.send_message(
            "You need to register first. Use `/register <player_id>`.",
            ephemeral=True,
        )
        return

    # Guard: active session
    if bot._active_session is not None:
        log.info(
            "/matches rejected — session already active (owner=%s)", bot._active_session
        )
        await interaction.response.send_message(
            "Another session is active. Please wait for it to finish.",
            ephemeral=True,
        )
        return

    # Guard: hourly rate limit (owner exempt)
    if user_id != OWNER_DISCORD_ID:
        max_info, _, _ = bot.registry.get_limits(user_id)
        allowed, secs = bot.usage.check_info_limit(user_id, max_info)
        if not allowed:
            mins = secs // 60
            secs = secs % 60
            log.info(
                "/matches rejected — %s (%s) rate limited (%dm %ds remaining)",
                interaction.user,
                user_id,
                mins,
                secs,
            )
            await interaction.response.send_message(
                f"You have used your maximum allowed usage. Refresh in {mins} minutes {secs} seconds.",
                ephemeral=True,
            )
            return

    bot._active_session = user_id
    bot.usage.record_info(user_id)
    log.info(
        "/matches session started — %s (%s), player_id=%d",
        interaction.user,
        user_id,
        player_id,
    )
    await interaction.response.defer()

    try:
        await _run_info_session(interaction, player_id)
    finally:
        bot._active_session = None
        log.info("/matches session ended — %s (%s)", interaction.user, user_id)


async def _fetch_page_details(
    page_matches: list,
    details: dict,
    api_calls: int,
    interaction: discord.Interaction,
) -> int:
    """Fetch match details for a page, skipping already-fetched ones. Returns new api_calls."""
    page_ids = [m.match_id for m in page_matches]
    missing_ids = [mid for mid in page_ids if mid not in details]
    if not missing_ids:
        return api_calls

    log.info("Fetching match details — match_ids=%s", missing_ids)
    cached_before = sum(1 for mid in missing_ids if bot.cache.get(mid) is not None)
    new_details = await bot.client.fetch_match_details_async(missing_ids, cache=bot.cache)
    details.update(new_details)
    api_calls += len(missing_ids) - cached_before
    log.info("Match details fetched — %d/%d retrieved", len(new_details), len(missing_ids))

    # Request parsing for unparsed matches
    unparsed = [
        mid
        for mid in missing_ids
        if mid not in details or not details[mid].radiant_gold_adv
    ]
    if unparsed:
        log.info("Requesting parse for unparsed matches — %s", unparsed)
        match_by_id = {m.match_id: m for m in page_matches}
        ids_list = "\n".join(
            f"- `{mid}` — {format_date_discord(match_by_id[mid].start_time)}"
            if mid in match_by_id
            else f"- `{mid}`"
            for mid in unparsed
        )
        try:
            await bot.client.request_parse_async(unparsed)
            api_calls += len(unparsed) * 10
            embed = discord.Embed(
                title="Unparsed Matches Detected",
                description=ids_list,
                color=discord.Color.orange(),
            )
            await interaction.channel.send(embed=embed)
            await interaction.channel.send(
                f"Requesting parsing for {len(unparsed)} match(es). "
                f"Please wait up to 5 minutes."
            )
        except Exception:
            log.warning("Parse request failed for %s", unparsed, exc_info=True)

    return api_calls


async def _run_info_session(interaction: discord.Interaction, player_id: int) -> None:
    user_id = interaction.user.id

    api_calls = 0

    # Fetch player profile
    log.info("Fetching player profile — player_id=%d", player_id)
    try:
        player = await bot.client.fetch_player_async(player_id)
        api_calls += 1
    except Exception as e:
        log.error(
            "Failed to fetch player profile — player_id=%d", player_id, exc_info=True
        )
        await interaction.followup.send(f"Failed to fetch player profile: {_api_error_msg(e)}")
        return

    profile = player.get("profile", {})
    name = profile.get("personaname", "Unknown")
    avatar = profile.get("avatarmedium")
    turbo_mmr = player.get("computed_mmr_turbo")
    log.info(
        "Player profile fetched — name=%s, turbo_mmr=%s, avatar=%s",
        name,
        turbo_mmr,
        bool(avatar),
    )

    # Fetch weekly win/loss
    wl = {"win": 0, "lose": 0}
    try:
        wl = await bot.client.fetch_wl_async(player_id, date=7)
        api_calls += 1
        log.info(
            "Weekly W/L fetched — win=%d, lose=%d", wl.get("win", 0), wl.get("lose", 0)
        )
    except Exception:
        log.warning(
            "Failed to fetch weekly W/L — player_id=%d", player_id, exc_info=True
        )

    # Fetch recent matches — request enough to cover the week for game time
    weekly_total = wl.get("win", 0) + wl.get("lose", 0)
    fetch_limit = max(MAX_MATCHES, weekly_total)
    log.info("Fetching recent matches — player_id=%d, limit=%d", player_id, fetch_limit)
    try:
        all_recent = await bot.client.fetch_recent_matches_async(
            player_id, limit=fetch_limit
        )
        api_calls += 1
    except Exception as e:
        log.error(
            "Failed to fetch recent matches — player_id=%d", player_id, exc_info=True
        )
        await interaction.followup.send(f"Failed to fetch recent matches: {_api_error_msg(e)}")
        return

    if not all_recent:
        log.info("No recent matches found — player_id=%d", player_id)
        await interaction.followup.send("No recent matches found.")
        return

    matches = all_recent[:MAX_MATCHES]
    log.info(
        "Fetched %d recent matches — displaying %d, match_ids=%s",
        len(all_recent),
        len(matches),
        [m.match_id for m in matches],
    )

    # Calculate weekly game time from the fetched matches
    cutoff = int(time.time()) - 7 * 86400
    weekly_seconds = sum(m.duration for m in all_recent if m.start_time >= cutoff)
    log.info("Weekly game time — total %d seconds", weekly_seconds)

    # Split matches into pages
    pages = [matches[i : i + PAGE_SIZE] for i in range(0, len(matches), PAGE_SIZE)]
    total_pages = len(pages)
    current_page = 0
    details: dict = {}

    # Fetch details for the first page
    api_calls = await _fetch_page_details(
        pages[0], details, api_calls, interaction
    )
    bot.usage.record_api_calls(user_id, api_calls)

    # Classify and send first page
    classified_page = build_classified_matches(pages[0], details, bot.heroes)
    log.info("Classified %d matches (page 1/%d)", len(classified_page), total_pages)

    summary_embeds = build_summary_embeds(
        name,
        turbo_mmr,
        classified_page,
        hero_icons=bot.hero_icons,
        avatar_url=avatar,
        weekly_wl=wl,
        weekly_seconds=weekly_seconds,
        page=0,
        total_pages=total_pages,
    )
    message = await interaction.followup.send(embeds=summary_embeds, wait=True)
    log.info("Summary embed sent — message_id=%s", message.id)

    # Add reactions: arrows (if multiple pages) then numbers
    if total_pages > 1:
        await message.add_reaction(LEFT_ARROW)
        await message.add_reaction(RIGHT_ARROW)
    for i in range(len(classified_page)):
        await message.add_reaction(NUMBER_EMOJIS[i])

    # Pagination loop — wait for arrow or number reaction
    arrow_emojis = [LEFT_ARROW, RIGHT_ARROW]

    while True:
        valid_emojis = NUMBER_EMOJIS[: len(classified_page)]
        if total_pages > 1:
            valid_emojis = valid_emojis + arrow_emojis

        def check_reaction(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                user.id == user_id
                and reaction.message.id == message.id
                and str(reaction.emoji) in valid_emojis
            )

        log.info(
            "Waiting for reaction from %s (%s) — page %d/%d",
            interaction.user,
            user_id,
            current_page + 1,
            total_pages,
        )

        try:
            reaction, _ = await bot.wait_for(
                "reaction_add", timeout=REACTION_TIMEOUT, check=check_reaction
            )
        except TimeoutError:
            log.info(
                "Match selection timed out after %.0fs — %s (%s)",
                REACTION_TIMEOUT,
                interaction.user,
                user_id,
            )
            return

        emoji = str(reaction.emoji)

        # Handle arrow navigation
        if emoji == LEFT_ARROW:
            prev_page_size = len(classified_page)
            current_page = (current_page - 1) % total_pages
        elif emoji == RIGHT_ARROW:
            prev_page_size = len(classified_page)
            current_page = (current_page + 1) % total_pages
        else:
            # Number selected — break out to detail view
            idx = NUMBER_EMOJIS.index(emoji)
            cm = classified_page[idx]
            log.info(
                "Match selected — %s (%s) picked match #%d on page %d (match_id=%d, hero=%s)",
                interaction.user,
                user_id,
                idx + 1,
                current_page + 1,
                cm.match.match_id,
                cm.hero_name,
            )
            break

        # Remove the user's arrow reaction so they can click it again
        await reaction.remove(interaction.user)

        # Navigating to a new page — fetch details lazily
        page_api_calls = await _fetch_page_details(
            pages[current_page], details, 0, interaction
        )
        if page_api_calls > 0:
            bot.usage.record_api_calls(user_id, page_api_calls)

        classified_page = build_classified_matches(
            pages[current_page], details, bot.heroes
        )
        log.info(
            "Page changed to %d/%d — classified %d matches",
            current_page + 1,
            total_pages,
            len(classified_page),
        )

        summary_embeds = build_summary_embeds(
            name,
            turbo_mmr,
            classified_page,
            hero_icons=bot.hero_icons,
            avatar_url=avatar,
            weekly_wl=wl,
            weekly_seconds=weekly_seconds,
            page=current_page,
            total_pages=total_pages,
        )
        await message.edit(embeds=summary_embeds)

        # Only update number reactions if page size changed (e.g. last page)
        new_page_size = len(classified_page)
        if new_page_size != prev_page_size:
            # Remove extra number reactions
            for i in range(new_page_size, prev_page_size):
                await message.clear_reaction(NUMBER_EMOJIS[i])
            # Add missing number reactions
            for i in range(prev_page_size, new_page_size):
                await message.add_reaction(NUMBER_EMOJIS[i])

    # Block detail view for unparsed matches
    is_parsed = cm.match_detail is not None and bool(cm.match_detail.radiant_gold_adv)
    if not is_parsed:
        log.info("Detail view rejected — match %d is not parsed", cm.match.match_id)
        await interaction.channel.send(
            "Sorry, this match has not been parsed by OpenDota yet."
        )
        return

    # Generate gold/XP advantage graph
    graph_filename = "advantage.png"
    gold_adv = cm.match_detail.radiant_gold_adv
    xp_adv = cm.match_detail.radiant_xp_adv
    graph_buf = generate_advantage_graph(
        gold_adv, xp_adv, is_radiant=cm.match.is_radiant,
    )
    graph_file = discord.File(fp=graph_buf, filename=graph_filename)

    # Send detail embed
    detail_embed = build_detail_embed(cm, graph_filename=graph_filename)
    detail_msg = await interaction.channel.send(embed=detail_embed, file=graph_file)
    log.info("Detail embed sent — message_id=%s", detail_msg.id)
    await detail_msg.add_reaction(BRAIN_EMOJI)

    # Wait for brain reaction from the requesting user
    log.info("Waiting for AI analysis reaction from %s (%s)", interaction.user, user_id)

    def check_brain(reaction: discord.Reaction, user: discord.User) -> bool:
        return (
            user.id == user_id
            and reaction.message.id == detail_msg.id
            and str(reaction.emoji) == BRAIN_EMOJI
        )

    try:
        await bot.wait_for("reaction_add", timeout=REACTION_TIMEOUT, check=check_brain)
    except TimeoutError:
        log.info(
            "AI analysis reaction timed out after %.0fs — %s (%s)",
            REACTION_TIMEOUT,
            interaction.user,
            user_id,
        )
        return

    log.info(
        "AI analysis requested — %s (%s), match_id=%d",
        interaction.user,
        user_id,
        cm.match.match_id,
    )

    # Guard: hourly LLM rate limit (owner exempt)
    if user_id != OWNER_DISCORD_ID:
        _, max_llm, _ = bot.registry.get_limits(user_id)
        allowed, secs = bot.usage.check_llm_limit(user_id, max_llm)
        if not allowed:
            mins = secs // 60
            secs = secs % 60
            log.info(
                "AI analysis rejected — %s (%s) rate limited (%dm %ds remaining)",
                interaction.user,
                user_id,
                mins,
                secs,
            )
            await interaction.channel.send(
                f"You have used your maximum allowed usage. Refresh in {mins} minutes {secs} seconds."
            )
            return

    # Run AI analysis
    await interaction.channel.send("\u23f3 Analyzing, please wait up to 60 seconds...")

    try:
        raw = bot.cache.get_raw(cm.match.match_id)
        if raw:
            log.info("Using cached raw data for match %d", cm.match.match_id)
            match_json = enrich_match_data(raw)
        else:
            log.info(
                "No cached raw data for match %d — using model dump", cm.match.match_id
            )
            detail = details.get(cm.match.match_id)
            match_json = detail.model_dump() if detail else {}

        # Find the requesting player's slot
        player_slot = None
        for m in pages[current_page]:
            if m.match_id == cm.match.match_id:
                player_slot = m.player_slot
                break

        team = "Radiant" if player_slot is not None and player_slot < 128 else "Dire"
        team_key = "radiant" if team == "Radiant" else "dire"
        log.info("Player slot=%s, team=%s", player_slot, team)

        player_data = {}
        if isinstance(match_json.get(team_key), list):
            for p in match_json[team_key]:
                if p.get("Account ID") == player_id:
                    player_data = p
                    break

        prompt = build_system_prompt(player_data, team, match_json)
        log.info(
            "Sending LLM request — match_id=%d, hero=%s",
            cm.match.match_id,
            cm.hero_name,
        )
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, analyze_match, prompt)
        bot.usage.record_llm(user_id)
        log.info(
            "LLM response received — sections: %s", [k for k, v in result.items() if v]
        )

        embeds = build_analysis_embeds(result)
        for embed in embeds:
            await interaction.channel.send(embed=embed)
        log.info("AI analysis embeds sent — %d embeds", len(embeds))
    except Exception as e:
        log.error(
            "AI analysis failed — match_id=%d: %s", cm.match.match_id, e, exc_info=True
        )
        await interaction.channel.send(f"AI analysis failed: {e}")


@app_commands.command(name="info", description="Show available commands and their API costs")
async def _info(interaction: discord.Interaction) -> None:
    log.info("/info by %s (%s)", interaction.user, interaction.user.id)

    embed = discord.Embed(
        title="Kaneko — Commands",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="/register <player_id>",
        value=(
            "Link your Discord account to your OpenDota player ID.\n"
            "API calls: **1**"
        ),
        inline=False,
    )
    embed.add_field(
        name="/matches",
        value=(
            "Show your last 20 matches with classification, stats, and graphs. "
            "React with a number to view match details, then with the brain emoji for AI analysis.\n"
            "API calls: **7+** (profile + W/L + recent + 5 match details per page)"
        ),
        inline=False,
    )
    embed.add_field(
        name="/parse",
        value=(
            "Scan your last 20 matches and request OpenDota to parse up to 4 unparsed replays. "
            "Parsed matches unlock detailed stats, graphs, and AI analysis.\n"
            "API calls: **21–61** (recent + up to 20 details + up to 40 for parse requests)\n"
            "Limit: **1 per hour**"
        ),
        inline=False,
    )
    embed.add_field(
        name="/usage",
        value=(
            "Show your lifetime command usage and remaining hourly limits.\n"
            "API calls: **0**"
        ),
        inline=False,
    )
    embed.add_field(
        name="/info",
        value=(
            "Show this help message.\n"
            "API calls: **0**"
        ),
        inline=False,
    )
    embed.set_footer(text="OpenDota API has a rate limit of 60 calls/min for free tier")
    await interaction.response.send_message(embed=embed, ephemeral=True)


PARSE_LIMIT = 4


@app_commands.command(
    name="parse", description="Request parsing for your recent unparsed matches"
)
async def _parse(interaction: discord.Interaction) -> None:
    user_id = interaction.user.id
    log.info("/parse by %s (%s)", interaction.user, user_id)

    if bot.registry.is_banned(user_id):
        await interaction.response.send_message("You have been banned.", ephemeral=True)
        return

    player_id = bot.registry.get(user_id)
    if player_id is None:
        log.info("/parse rejected — %s (%s) not registered", interaction.user, user_id)
        await interaction.response.send_message(
            "You need to register first. Use `/register <player_id>`.",
            ephemeral=True,
        )
        return

    # Guard: hourly parse rate limit (owner exempt)
    if user_id != OWNER_DISCORD_ID:
        _, _, max_parse = bot.registry.get_limits(user_id)
        allowed, secs = bot.usage.check_parse_limit(user_id, max_parse)
        if not allowed:
            mins = secs // 60
            secs = secs % 60
            log.info(
                "/parse rejected — %s (%s) rate limited (%dm %ds remaining)",
                interaction.user,
                user_id,
                mins,
                secs,
            )
            await interaction.response.send_message(
                f"You have used your maximum allowed usage. Refresh in {mins} minutes {secs} seconds.",
                ephemeral=True,
            )
            return

    bot.usage.record_parse(user_id)
    await interaction.response.defer()

    api_calls = 0

    # Fetch latest 20 matches
    try:
        recent = await bot.client.fetch_recent_matches_async(player_id, limit=MAX_MATCHES)
        api_calls += 1
    except Exception as e:
        log.error("/parse failed to fetch recent matches — player_id=%d", player_id, exc_info=True)
        await interaction.followup.send(f"Failed to fetch recent matches: {_api_error_msg(e)}")
        return

    if not recent:
        await interaction.followup.send("No recent matches found.")
        return

    # Fetch match details to check parse status
    match_ids = [m.match_id for m in recent]
    try:
        details = await bot.client.fetch_match_details_async(match_ids, cache=bot.cache)
        cached_count = sum(1 for mid in match_ids if bot.cache.get(mid) is not None)
        api_calls += len(match_ids) - cached_count
    except Exception as e:
        log.error("/parse failed to fetch match details", exc_info=True)
        await interaction.followup.send(f"Failed to fetch match details: {_api_error_msg(e)}")
        return

    # Find unparsed matches
    unparsed = [
        m for m in recent
        if m.match_id not in details or not details[m.match_id].radiant_gold_adv
    ]

    if not unparsed:
        embed = discord.Embed(
            title="All Parsed",
            description="All 20 recent matches are already parsed.",
            color=discord.Color.green(),
        )
        bot.usage.record_api_calls(user_id, api_calls)
        await interaction.followup.send(embed=embed)
        return

    # Send up to 4 for parsing
    to_parse = unparsed[:PARSE_LIMIT]
    total_unparsed = len(unparsed)
    parse_ids = [m.match_id for m in to_parse]

    log.info(
        "/parse sending %d/%d unparsed matches — %s",
        len(to_parse), total_unparsed, parse_ids,
    )

    try:
        await bot.client.request_parse_async(parse_ids)
        api_calls += len(parse_ids) * 10
    except Exception as e:
        log.error("/parse request failed — %s", parse_ids, exc_info=True)
        await interaction.followup.send(f"Parse request failed: {_api_error_msg(e)}")
        return

    bot.usage.record_api_calls(user_id, api_calls)

    embeds = build_parse_embeds(
        to_parse, total_unparsed,
        heroes=bot.heroes,
        hero_icons=bot.hero_icons,
    )
    await interaction.followup.send(embeds=embeds)
    log.info("/parse complete — sent %d embeds", len(embeds))


def run_bot() -> None:
    load_dotenv()

    import colorlog

    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            fmt="%(asctime)s %(log_color)s%(levelname)-8s%(reset)s %(cyan)s[%(name)s]%(reset)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                "DEBUG": "white",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)

    token = os.environ.get("DISCORD_TOKEN", "")
    if not token:
        log.error("DISCORD_TOKEN is not set. Add it to your .env file.")
        return
    bot.run(token, log_handler=None)
