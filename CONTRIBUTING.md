# Contributing

Thanks for your interest in improving the Unity-to-Roblox converter!

## Getting Started

```bash
# Clone the repo
git clone https://github.com/jiazou/unity-roblox-game-converter.git
cd unity-roblox-game-converter

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Optional: assimp (for FBX vertex color baking)

```bash
# macOS
brew install assimp

# Ubuntu/Debian
sudo apt-get install libassimp-dev

# Windows
# Download from https://github.com/assimp/assimp/releases
```

## Running Tests

```bash
python -m pytest tests/ -v
```

The test suite (~1200 tests) should complete in under 10 seconds.
Tests that require external tools (assimp CLI) are automatically skipped
if the tool is not installed.

## Project Structure

```
converter.py            # Batch CLI (end-to-end, no interaction)
convert_interactive.py  # Phase-based CLI (used by /convert-unity skill)
config.py               # All configuration constants
modules/                # Pipeline modules (24 modules)
bridge/                 # Luau runtime shim modules (9 modules)
tests/                  # Test suite
docs/                   # Design docs and status tracking
```

See `CLAUDE.md` for architecture details and the pipeline phase breakdown.

## Making Changes

1. Create a feature branch from `main`
2. Make your changes
3. Add or update tests for any new/changed behavior
4. Run the full test suite: `python -m pytest tests/ -v`
5. Submit a pull request with a clear description of what and why

### Code Style

- Python: PEP 8, type hints on public functions
- Luau (bridge/): Follow existing module patterns
- No module in `modules/` imports another module — all wiring happens
  in the orchestrators. The exception is `conversion_helpers.py` (see CLAUDE.md).

### What Makes a Good PR

- Focused: one logical change per PR
- Tested: new behavior has tests, existing tests still pass
- Documented: update docs if you change pipeline behavior or add modules

## Reporting Issues

Open a GitHub issue with:
- What you were converting (Unity version, project size)
- What went wrong (error message, unexpected output)
- Steps to reproduce
- The `conversion_report.json` if available (redact any API keys)

## Architecture Overview

The converter is a 5-phase pipeline:

1. **Discovery** — parse `.unity`/`.prefab` YAML files
2. **Inventory** — catalog assets, build GUID index
3. **Processing** — map materials, transpile C# → Luau, decimate meshes
4. **Assembly** — build `.rbxl` XML, inject bridge modules, generate bootstrap
5. **Upload** — upload assets to Roblox Cloud, inject MeshLoader, generate report

Each phase's output feeds the next. The interactive CLI (`convert_interactive.py`)
pauses between phases for human review; the batch CLI (`converter.py`) runs
everything end-to-end.
