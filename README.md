# Kaneko

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A CLI tool that fetches your recent Dota 2 matches from the [OpenDota API](https://docs.opendota.com/) and classifies them with performance metrics.

## Features

- **Match classification** — categorises each game as Stomp, Stomped, Comeback, Throw, or Even based on gold advantage curves
- **Contribution metrics** — fight participation, damage share, vision, stuns, and lane efficiency as team percentages
- **Auto-parse requests** — automatically queues unparsed replays for parsing via OpenDota
- **Turbo MMR** — displays your computed turbo MMR from OpenDota

## Output

```
Player: Kv
Turbo MMR: 3856

┌───┬────────┬──────────────────┬─────────┬──────────┬───────────────────┬─────────┬──────────┬─────────┐
│ # │ Result │ Hero             │ K/D/A   │ Duration │ Date              │ Type    │ Max Lead │ Max Def │
├───┼────────┼──────────────────┼─────────┼──────────┼───────────────────┼─────────┼──────────┼─────────┤
│ 1 │  Win   │ Pudge (Off)      │ 12/4/15 │ 35:22    │ 2:14pm 17 May ... │ Stomp   │   18.2k  │  -1.3k  │
│ 2 │  Loss  │ Lion (Mid)       │ 19/10/13│ 44:22    │ 1:30pm 17 May ... │ Stomped │   10.1k  │ -40.2k  │
└───┴────────┴──────────────────┴─────────┴──────────┴───────────────────┴─────────┴──────────┴─────────┘
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```sh
git clone https://github.com/Kvyii/Kaneko.git
cd Kaneko
uv sync
```

Create a `config.json` with your [OpenDota player ID](https://www.opendota.com/):

```json
{
    "player_id": 123456789,
    "turbo_only": true
}
```

Run:

```sh
uv run dota
```

## Project Structure

```
src/dota/
├── api/client.py          # OpenDota API client
├── models/match.py        # Pydantic data models
├── analysis/classifier.py # Match classification & contribution logic
├── display/table.py       # Rich terminal table rendering
├── config.py              # Configuration loading
└── __main__.py            # Entrypoint
```

## Data

The `data/` folder contains static JSON from [odota/dotaconstants](https://github.com/odota/dotaconstants) (MIT license) for hero names and game constants.

## License

[MIT](LICENSE)
