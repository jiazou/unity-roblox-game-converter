# unity-roblox-game-converter

A Python tool that converts Unity game projects into Roblox place files (`.rbxl`).

It walks a Unity project directory, extracts assets, parses scenes and prefabs,
transpiles C# MonoBehaviour scripts to Luau (optionally using Claude AI), and
writes a ready-to-open `.rbxl` file for Roblox Studio.

---

## Module Overview

| Module | Main Function | Description |
|---|---|---|
| `asset_extractor` | `extract_assets(unity_project_path)` | Discovers textures, meshes, audio, materials, and animations; returns an `AssetManifest`. |
| `scene_parser` | `parse_scene(scene_path)` | Parses a `.unity` scene YAML file into a tree of `SceneNode` objects. |
| `prefab_parser` | `parse_prefabs(unity_project_path)` | Finds and parses all `.prefab` files; returns a `PrefabLibrary`. |
| `code_transpiler` | `transpile_scripts(unity_project_path, ...)` | Converts C# scripts to Luau via rule-based transforms or Claude AI. |
| `rbxl_writer` | `write_rbxl(parts, scripts, output_path)` | Serialises geometry and scripts into a valid `.rbxl` XML place file. |
| `report_generator` | `generate_report(report, output_path)` | Writes a JSON conversion report and prints a human-readable summary. |

`converter.py` is the orchestrator — it imports all modules, calls them in order,
and passes data between them. `config.py` holds all paths, keys, and options.

---

## Requirements

- Python 3.11+
- Dependencies listed in `requirements.txt`

```bash
pip install -r requirements.txt
```

---

## How to Run

```bash
python converter.py <unity_project_path> <output_dir> [OPTIONS]
```

### Arguments

| Argument | Description |
|---|---|
| `unity_project_path` | Path to the root of your Unity project (must contain an `Assets/` folder) |
| `output_dir` | Directory where `converted_place.rbxl` and `conversion_report.json` will be written |

### Options

| Flag | Default | Description |
|---|---|---|
| `--use-ai` / `--no-ai` | from `config.py` | Use Claude (Anthropic) for C# → Luau transpilation |
| `--api-key KEY` | `$ANTHROPIC_API_KEY` | Anthropic API key |
| `--verbose` / `--no-verbose` | `True` | Include per-script detail in the JSON report |

### Examples

```bash
# Rule-based transpilation (no API key needed)
python converter.py ./MyUnityProject ./roblox_output --no-ai

# AI-assisted transpilation with Claude
ANTHROPIC_API_KEY=sk-ant-... python converter.py ./MyUnityProject ./roblox_output --use-ai

# Specify API key inline
python converter.py ./MyUnityProject ./roblox_output --use-ai --api-key sk-ant-...
```

### Output

```
roblox_output/
├── converted_place.rbxl    ← Open in Roblox Studio
└── conversion_report.json  ← Full conversion summary
```

---

## Configuration

Edit `config.py` to change defaults (paths, model name, confidence threshold, etc.)
without modifying any pipeline module.
