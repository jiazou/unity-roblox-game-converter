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
| `guid_resolver` | `build_guid_index(unity_project_path)` | Builds a full bidirectional GUID ↔ asset-path index from `.meta` files. Detects orphans and duplicates. |
| `scene_parser` | `parse_scene(scene_path)` | Parses a `.unity` scene YAML file into a tree of `SceneNode` objects. |
| `prefab_parser` | `parse_prefabs(unity_project_path)` | Finds and parses all `.prefab` files; returns a `PrefabLibrary`. |
| `material_mapper` | `map_materials(unity_path, out_dir)` | Parses Unity `.mat` files, resolves shaders/textures, produces Roblox materials. |
| `code_transpiler` | `transpile_scripts(unity_project_path, ...)` | Converts C# scripts to Luau via rule-based transforms or Claude AI. |
| `mesh_decimator` | `decimate_meshes(mesh_paths, output_dir)` | Conservative mesh decimation — only reduces faces when above the Roblox 10k limit. |
| `roblox_uploader` | `upload_to_roblox(rbxl_path, ...)` | Uploads `.rbxl` and textures to Roblox via Open Cloud API. Requires a Roblox API key. |
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
| `--roblox-api-key KEY` | `$ROBLOX_API_KEY` | Roblox Open Cloud API key (**required** for portal upload) |
| `--universe-id ID` | — | Roblox universe (experience) ID for upload |
| `--place-id ID` | — | Roblox place ID for upload |
| `--decimate` / `--no-decimate` | `True` | Conservative mesh decimation for Roblox polygon limits |

### Examples

```bash
# Rule-based transpilation (no API key needed)
python converter.py ./MyUnityProject ./roblox_output --no-ai

# AI-assisted transpilation with Claude
ANTHROPIC_API_KEY=sk-ant-... python converter.py ./MyUnityProject ./roblox_output --use-ai

# Specify API key inline
python converter.py ./MyUnityProject ./roblox_output --use-ai --api-key sk-ant-...

# Upload to Roblox (requires Open Cloud API key)
python converter.py ./MyUnityProject ./roblox_output \
    --roblox-api-key YOUR_ROBLOX_KEY \
    --universe-id 123456 \
    --place-id 789012
```

### Output

```
roblox_output/
├── converted_place.rbxl    ← Open in Roblox Studio
├── meshes/                 ← Decimated meshes (when --decimate is on)
└── conversion_report.json  ← Full conversion summary
```

### Portal Upload

To upload directly to Roblox, you need a **Roblox Open Cloud API key** with
publish permissions. Without a valid key, the converter writes the `.rbxl`
file locally and you can open it manually in Roblox Studio.

1. Create an API key at https://create.roblox.com/credentials
2. Grant it the **Place — Write** permission for your experience
3. Pass it via `--roblox-api-key` or the `ROBLOX_API_KEY` environment variable

### Mesh Decimation

Roblox limits MeshParts to 10 000 polygons. The converter applies
**conservative** decimation by default:

- Meshes already under the limit are copied unchanged.
- Over-budget meshes are reduced to 8 000 faces (leaving headroom).
- A quality floor of 60% prevents visually destructive simplification.
- Original files are never modified — decimated copies go to `meshes/`.

Disable with `--no-decimate` if you prefer to handle mesh optimization yourself.

---

## Configuration

Edit `config.py` to change defaults (paths, model name, confidence threshold, etc.)
without modifying any pipeline module.
