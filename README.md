# DotA Match Tracker

Fetches and displays your recent Dota 2 matches using the OpenDota API.

## Setup (Windows, fresh install)

### 1. Install uv

Open PowerShell and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen your terminal after installing so `uv` is on your PATH.

### 2. Clone the repo

```powershell
git clone <repo-url>
cd DotA
```

### 3. Install dependencies

```powershell
uv sync
```

This will automatically download the correct Python version and install all dependencies into a `.venv`.

### 4. Configure your player ID

Edit `config.json` and set your OpenDota player ID (the number from your profile URL, e.g. `https://www.opendota.com/players/012345678`):

```json
{
    "player_id": 012345678
}
```

### 5. Run

```powershell
uv run main.py
```

## Data

The `data/` folder contains static JSON files from [odota/dotaconstants](https://github.com/odota/dotaconstants) (MIT license). These provide hero names, game mode labels, and other Dota 2 constants.

## VSCode setup

1. Install the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python)
2. Open the project folder in VSCode
3. VSCode should auto-detect the `.venv` — if not, open the command palette (`Ctrl+Shift+P`) and select **Python: Select Interpreter**, then choose the `.venv` in the project folder
