# Kaneko

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Kaneko is a Discord bot that analyzes your Dota 2 matches. It pulls data from the [OpenDota API](https://docs.opendota.com/), classifies your games, breaks down your performance, and uses an LLM to give you a detailed analysis of any match — all from within Discord.

## Features

- **Match History** — View your 5 most recent matches with win/loss, hero, K/D/A, duration, and match classification
- **Match Classification** — Each game is categorized as a Stomp, Stomped, Comeback, Throw, or Even based on gold advantage curves
- **Detailed Match Stats** — Select any match to see full stats: GPM, XPM, last hits, denies, and contribution percentages for damage, vision, stuns, tower damage, and more
- **AI Match Analysis** — React with the brain emoji to get an LLM-powered breakdown of any match covering the overall match dynamics, your individual performance, and the core reasons for the win or loss
- **Player Registration** — Link your Discord account to your OpenDota profile with `/register`
- **Weekly Stats** — See your win/loss record for the past 7 days
- **Auto-Parse** — Automatically requests OpenDota to parse unparsed replays
- **Rate Limiting** — Per-user hourly limits to prevent API abuse
- **Match Caching** — Caches parsed match data locally to speed up repeated lookups

## Screenshots

![Kaneko in action](assets/screenshots/kaneko_app.png)

## Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A Discord bot token
- An OpenRouter API key

### Installation

```sh
git clone https://github.com/Kvyii/Kaneko.git
cd Kaneko
uv sync
```

### Configuration

Copy the environment template and fill in your credentials:

```sh
cp .env.template .env
```

Open `.env` and set the following values:

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Your Discord bot token from the [Discord Developer Portal](https://discord.com/developers/applications) |
| `OPENROUTER_API_KEY` | Your API key from [OpenRouter](https://openrouter.ai/) |
| `OPENROUTER_MODEL` | The model to use for match analysis. Defaults to `deepseek/deepseek-v4-pro` |
| `DISCORD_GUILD_IDS` | Comma-separated guild IDs for instant slash command sync. Optional — without it, commands sync globally (can take up to an hour) |

### Running the Bot

```sh
uv run dota-bot
```

## Usage

| Command | Description |
|---|---|
| `/register <player_id>` | Link your Discord account to your [OpenDota](https://www.opendota.com/) player ID |
| `/info` | Show your 5 most recent matches. React with a number emoji to view match details, then react with the brain emoji for AI analysis |
| `/usage` | View your lifetime bot usage stats and remaining hourly rate limits |

## Data

The `data/` folder contains static JSON from [odota/dotaconstants](https://github.com/odota/dotaconstants) (MIT license) for hero names, items, game modes, and rank tiers.

## License

[MIT](LICENSE)
