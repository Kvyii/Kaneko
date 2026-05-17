import asyncio
import json
import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from dota.api.client import OpenDotaClient
from dota.analysis.classifier import build_classified_matches
from dota.cache import MatchCache
from dota.llm.client import analyze_match
from dota.llm.prepare import enrich_match_data
from dota.prompts.match_analysis import build_system_prompt

from dota.bot.players import PlayerRegistry
from dota.bot.embeds import build_summary_embeds, build_detail_embed, build_analysis_embeds
from dota.bot.usage import UsageTracker

log = logging.getLogger("dota.bot")

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

NUMBER_EMOJIS = ["1\ufe0f\u20e3", "2\ufe0f\u20e3", "3\ufe0f\u20e3", "4\ufe0f\u20e3", "5\ufe0f\u20e3"]
BRAIN_EMOJI = "\U0001f9e0"
REACTION_TIMEOUT = 15.0  # seconds
OWNER_DISCORD_ID = 227439391147032576


STEAM_CDN = "https://cdn.cloudflare.steamstatic.com"


def _load_heroes() -> dict[str, str]:
    with open(DATA_DIR / "heroes.json") as f:
        heroes = json.load(f)
    return {
        str(hero_id): data["localized_name"]
        for hero_id, data in heroes.items()
    }


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

        # Active session lock: only one /info at a time
        self._active_session: int | None = None  # discord user id of active session owner

    async def setup_hook(self) -> None:
        self.tree.add_command(_register)
        self.tree.add_command(_info)
        self.tree.add_command(_usage)
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
    log.info("/register by %s (%s) — player_id=%d", interaction.user, interaction.user.id, player_id)
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
    log.info("/register success — %s (%s) linked to %s (player_id=%d)", interaction.user, interaction.user.id, name, player_id)

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
    bot.usage.record_command(user_id, "usage")

    stats = bot.usage.get_usage(user_id)
    max_info, max_llm = bot.registry.get_limits(user_id)

    # Lifetime command usage
    cmds = stats["commands"]
    cmd_lines = []
    for name, count in sorted(cmds.items()):
        cmd_lines.append(f"/{name}: **{count}**")
    cmd_text = "\n".join(cmd_lines) if cmd_lines else "None"

    # Remaining calls this hour
    info_remaining = max(0, max_info - stats["info_this_hour"])
    llm_remaining = max(0, max_llm - stats["llm_this_hour"])
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
        name="API Calls (lifetime)",
        value=f"**{stats['api_calls']}**",
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(
        name="Remaining This Hour",
        value=(
            f"/info: **{info_remaining}** / {max_info}\n"
            f"AI analysis: **{llm_remaining}** / {max_llm}\n"
            f"Refresh in **{mins}m {secs}s**"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="info", description="Show your recent Dota 2 matches")
async def _info(interaction: discord.Interaction) -> None:
    user_id = interaction.user.id
    log.info("/info by %s (%s)", interaction.user, user_id)

    # Guard: registration
    player_id = bot.registry.get(user_id)
    if player_id is None:
        log.info("/info rejected — %s (%s) not registered", interaction.user, user_id)
        await interaction.response.send_message(
            "You need to register first. Use `/register <player_id>`.",
            ephemeral=True,
        )
        return

    # Guard: active session
    if bot._active_session is not None:
        log.info("/info rejected — session already active (owner=%s)", bot._active_session)
        await interaction.response.send_message(
            "Another session is active. Please wait for it to finish.",
            ephemeral=True,
        )
        return

    # Guard: hourly info rate limit (owner exempt)
    if user_id != OWNER_DISCORD_ID:
        max_info, _ = bot.registry.get_limits(user_id)
        allowed, secs = bot.usage.check_info_limit(user_id, max_info)
        if not allowed:
            mins = secs // 60
            secs = secs % 60
            log.info("/info rejected — %s (%s) rate limited (%dm %ds remaining)", interaction.user, user_id, mins, secs)
            await interaction.response.send_message(
                f"You have used your maximum allowed usage. Refresh in {mins} minutes {secs} seconds.",
                ephemeral=True,
            )
            return

    bot._active_session = user_id
    bot.usage.record_info(user_id)
    log.info("/info session started — %s (%s), player_id=%d", interaction.user, user_id, player_id)
    await interaction.response.defer()

    try:
        await _run_info_session(interaction, player_id)
    finally:
        bot._active_session = None
        log.info("/info session ended — %s (%s)", interaction.user, user_id)


async def _run_info_session(interaction: discord.Interaction, player_id: int) -> None:
    user_id = interaction.user.id

    api_calls = 0

    # Fetch player profile
    log.info("Fetching player profile — player_id=%d", player_id)
    try:
        player = await bot.client.fetch_player_async(player_id)
        api_calls += 1
    except Exception:
        log.error("Failed to fetch player profile — player_id=%d", player_id, exc_info=True)
        await interaction.followup.send("Failed to reach OpenDota API.")
        return

    profile = player.get("profile", {})
    name = profile.get("personaname", "Unknown")
    avatar = profile.get("avatarmedium")
    turbo_mmr = player.get("computed_mmr_turbo")
    log.info("Player profile fetched — name=%s, turbo_mmr=%s, avatar=%s", name, turbo_mmr, bool(avatar))

    # Fetch weekly win/loss
    wl = {"win": 0, "lose": 0}
    try:
        wl = await bot.client.fetch_wl_async(player_id, date=7)
        api_calls += 1
        log.info("Weekly W/L fetched — win=%d, lose=%d", wl.get("win", 0), wl.get("lose", 0))
    except Exception:
        log.warning("Failed to fetch weekly W/L — player_id=%d", player_id, exc_info=True)

    # Fetch recent matches
    log.info("Fetching recent matches — player_id=%d, limit=5", player_id)
    try:
        matches = await bot.client.fetch_recent_matches_async(player_id, limit=5)
        api_calls += 1
    except Exception:
        log.error("Failed to fetch recent matches — player_id=%d", player_id, exc_info=True)
        await interaction.followup.send("Failed to fetch matches.")
        return

    if not matches:
        log.info("No recent matches found — player_id=%d", player_id)
        await interaction.followup.send("No recent matches found.")
        return

    log.info("Fetched %d recent matches — match_ids=%s", len(matches), [m.match_id for m in matches])

    # Fetch match details
    match_ids = [m.match_id for m in matches]
    log.info("Fetching match details — match_ids=%s", match_ids)
    cached_before = sum(1 for mid in match_ids if bot.cache.get(mid) is not None)
    details = await bot.client.fetch_match_details_async(match_ids, cache=bot.cache)
    api_calls += len(match_ids) - cached_before
    log.info("Match details fetched — %d/%d retrieved", len(details), len(match_ids))

    # Request parsing for unparsed matches
    unparsed = [
        mid for mid in match_ids
        if mid not in details or not details[mid].radiant_gold_adv
    ]
    if unparsed:
        log.info("Requesting parse for unparsed matches — %s", unparsed)
        ids_list = "\n".join(f"- `{mid}`" for mid in unparsed)
        try:
            await bot.client.request_parse_async(unparsed)
            api_calls += len(unparsed)
            await interaction.channel.send(
                f"Discovered unparsed matches:\n{ids_list}\n\n"
                f"Requesting the most recent {len(unparsed)} match(es) for parsing. "
                f"Please wait up to 5 minutes."
            )
        except Exception:
            log.warning("Parse request failed for %s", unparsed, exc_info=True)

    # Record API usage
    bot.usage.record_api_calls(user_id, api_calls)

    # Classify
    classified = build_classified_matches(matches, details, bot.heroes)
    log.info("Classified %d matches", len(classified))

    # Send summary embeds
    summary_embeds = build_summary_embeds(
        name, turbo_mmr, classified,
        hero_icons=bot.hero_icons, avatar_url=avatar,
        weekly_wl=wl,
    )
    message = await interaction.followup.send(embeds=summary_embeds, wait=True)
    log.info("Summary embed sent — message_id=%s", message.id)

    # Add number reactions for each match
    for i in range(len(classified)):
        await message.add_reaction(NUMBER_EMOJIS[i])

    # Wait for number reaction from the requesting user
    log.info("Waiting for match selection reaction from %s (%s)", interaction.user, user_id)

    def check_number(reaction: discord.Reaction, user: discord.User) -> bool:
        return (
            user.id == user_id
            and reaction.message.id == message.id
            and str(reaction.emoji) in NUMBER_EMOJIS[:len(classified)]
        )

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=REACTION_TIMEOUT, check=check_number)
    except TimeoutError:
        log.info("Match selection timed out after %.0fs — %s (%s)", REACTION_TIMEOUT, interaction.user, user_id)
        return

    idx = NUMBER_EMOJIS.index(str(reaction.emoji))
    cm = classified[idx]
    log.info("Match selected — %s (%s) picked match #%d (match_id=%d, hero=%s)",
             interaction.user, user_id, idx + 1, cm.match.match_id, cm.hero_name)

    # Send detail embed
    hero_icon = bot.hero_icons.get(str(cm.match.hero_id))
    detail_embed = build_detail_embed(cm, hero_icon_url=hero_icon)
    detail_msg = await interaction.channel.send(embed=detail_embed)
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
        log.info("AI analysis reaction timed out after %.0fs — %s (%s)", REACTION_TIMEOUT, interaction.user, user_id)
        return

    log.info("AI analysis requested — %s (%s), match_id=%d", interaction.user, user_id, cm.match.match_id)

    # Guard: hourly LLM rate limit (owner exempt)
    if user_id != OWNER_DISCORD_ID:
        _, max_llm = bot.registry.get_limits(user_id)
        allowed, secs = bot.usage.check_llm_limit(user_id, max_llm)
        if not allowed:
            mins = secs // 60
            secs = secs % 60
            log.info("AI analysis rejected — %s (%s) rate limited (%dm %ds remaining)",
                     interaction.user, user_id, mins, secs)
            await interaction.channel.send(
                f"You have used your maximum allowed usage. Refresh in {mins} minutes {secs} seconds."
            )
            return

    # Run AI analysis
    is_parsed = cm.match_detail is not None and bool(cm.match_detail.radiant_gold_adv)
    if not is_parsed:
        log.info("AI analysis rejected — match %d is not parsed", cm.match.match_id)
        await interaction.channel.send(
            "Sorry, this match has not been parsed by OpenDota yet."
        )
        return
    await interaction.channel.send(
        "\u23f3 Analyzing, please wait up to 60 seconds..."
    )

    try:
        raw = bot.cache.get_raw(cm.match.match_id)
        if raw:
            log.info("Using cached raw data for match %d", cm.match.match_id)
            match_json = enrich_match_data(raw)
        else:
            log.info("No cached raw data for match %d — using model dump", cm.match.match_id)
            detail = details.get(cm.match.match_id)
            match_json = detail.model_dump() if detail else {}

        # Find the requesting player's slot
        player_slot = None
        for m in matches:
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
        log.info("Sending LLM request — match_id=%d, hero=%s", cm.match.match_id, cm.hero_name)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, analyze_match, prompt)
        bot.usage.record_llm(user_id)
        log.info("LLM response received — sections: %s", [k for k, v in result.items() if v])

        embeds = build_analysis_embeds(result)
        for embed in embeds:
            await interaction.channel.send(embed=embed)
        log.info("AI analysis embeds sent — %d embeds", len(embeds))
    except Exception as e:
        log.error("AI analysis failed — match_id=%d: %s", cm.match.match_id, e, exc_info=True)
        await interaction.channel.send(f"AI analysis failed: {e}")


def run_bot() -> None:
    load_dotenv()

    import colorlog

    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        fmt="%(asctime)s %(log_color)s%(levelname)-8s%(reset)s %(cyan)s[%(name)s]%(reset)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "white",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    ))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)

    token = os.environ.get("DISCORD_TOKEN", "")
    if not token:
        log.error("DISCORD_TOKEN is not set. Add it to your .env file.")
        return
    bot.run(token, log_handler=None)
