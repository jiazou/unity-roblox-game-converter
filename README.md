# unity-roblox-game-converter

A Unity-to-Roblox game converter available as an **interactive Claude Code skill**
(`/convert-unity`) or as a standalone batch CLI. It walks a Unity project
directory, extracts assets, parses scenes and prefabs, transpiles C#
MonoBehaviour scripts to Luau (optionally using Claude AI), and writes a
ready-to-open `.rbxl` file for Roblox Studio.

---

## Quick Start

### Interactive skill (recommended)

In Claude Code, run:

```
/convert-unity
```

The skill walks you through each conversion phase, pausing at decision points:
- **Scene selection** — pick which scenes to include
- **Material review** — decide how to handle unconvertible materials
- **Script triage** — review flagged C# → Luau transpilations (accept, retry with AI, edit, skip)
- **Mesh quality** — confirm decimation results
- **Upload** — optionally push to Roblox Cloud

Conversion state is persisted to `<output_dir>/.convert_state.json`, so you can
resume a partially completed conversion or re-run individual phases.

### Batch CLI (no interaction)

```bash
python converter.py ./MyUnityProject ./roblox_output
```

Runs the full pipeline end-to-end without pausing. Best for CI/CD or when you
don't need to review intermediate results.

---

## Module Overview

### Pipeline modules

| Module | Main Function | Description |
|---|---|---|
| `scene_parser` | `parse_scene(scene_path)` | Parses a `.unity` scene YAML file into a tree of `SceneNode` objects. |
| `prefab_parser` | `parse_prefabs(unity_project_path)` | Finds and parses all `.prefab` files; returns a `PrefabLibrary`. |
| `asset_extractor` | `extract_assets(unity_project_path)` | Discovers textures, meshes, audio, materials, and animations; returns an `AssetManifest`. |
| `guid_resolver` | `build_guid_index(unity_project_path)` | Builds a full bidirectional GUID ↔ asset-path index from `.meta` files. Detects orphans and duplicates. |
| `material_mapper` | `map_materials(unity_path, out_dir)` | Parses Unity `.mat` files, resolves shaders/textures, produces Roblox materials. |
| `code_transpiler` | `transpile_scripts(unity_project_path, ...)` | Converts C# scripts to Luau via Claude AI (requires Anthropic API key). |
| `code_validator` | `validate_luau(source, filename)` | Validates generated Luau for syntax errors (block balance, residual C#). |
| `mesh_decimator` | `decimate_meshes(mesh_paths, output_dir)` | Conservative mesh decimation — only reduces faces when above the Roblox 10k limit. |
| `vertex_color_baker` | `bake_vertex_colors(mesh_paths, out_dir)` | Rasterises mesh vertex colors to UV-space textures (OBJ/PLY/GLB). |
| `scriptable_object_converter` | `convert_asset_files(unity_path)` | Converts Unity `.asset` ScriptableObjects to Luau data table ModuleScripts. |
| `animation_converter` | `convert_animations(scenes, guid_index, path)` | Parses Animator controllers/clips, generates Luau config tables and AnimatorBridge. |
| `ui_translator` | `translate_ui_hierarchy(roots)` | Converts Unity Canvas/RectTransform UI to Roblox ScreenGui/UDim2 hierarchy. |
| `conversion_helpers` | `scene_nodes_to_parts(...)`, `generate_bootstrap_script(...)` | Transforms parsed Unity nodes to Roblox parts; generates GameBootstrap lifecycle script. |
| `rbxl_writer` | `write_rbxl(parts, scripts, output_path)` | Serialises geometry and scripts into a valid `.rbxl` XML place file. |
| `rbxl_binary_writer` | `xml_to_binary(xml_path, binary_path)` | Converts XML `.rbxl` to Roblox binary format for Open Cloud upload. |
| `roblox_uploader` | `upload_to_roblox(rbxl_path, ...)` | Uploads assets and `.rbxl` to Roblox via Open Cloud API. Injects MeshLoader script. |
| `report_generator` | `generate_report(report, output_path)` | Writes a JSON conversion report and prints a human-readable summary. |

### Infrastructure modules

| Module | Description |
|---|---|
| `unity_yaml_utils` | Shared YAML parsing for scene/prefab files (document separators, classIDs, vector/quaternion extraction). |
| `api_mappings` | Unity C# → Roblox Luau API mapping tables (130+ call mappings, 15 lifecycle hooks). |
| `llm_cache` | SHA-256-based disk cache for LLM responses with TTL-based eviction. |
| `retry` | Exponential backoff retry decorator for transient network failures. |

### Entry points

| File | Purpose |
|---|---|
| `converter.py` | Batch CLI — runs all phases end-to-end, no interaction |
| `convert_interactive.py` | Phase-based CLI — called by the `/convert-unity` skill, one phase at a time with JSON output |
| `config.py` | All paths, keys, and tunable options |

---

## Requirements

- Python 3.11+
- Dependencies listed in `requirements.txt`

```bash
pip install -r requirements.txt
```

---

## How to Run

### Option A: Interactive skill (`/convert-unity`)

The recommended way to run a conversion. The skill asks you for the Unity
project path and output directory, then guides you through each phase:

1. **Discover** — scans scenes and prefabs, lets you choose which to include
2. **Inventory** — catalogs assets and GUIDs, flags duplicates/orphans
3. **Materials** — converts materials, presents unconvertible ones for review
4. **Transpile** — converts C# to Luau, shows flagged scripts for triage
5. **Validate** — checks generated Luau for syntax errors
6. **Assemble** — builds the .rbxl file
7. **Upload** — (optional) pushes to Roblox Cloud
8. **Report** — generates the final conversion summary

Each phase can be re-run independently if you change your mind or want to
try different settings.

### Option B: Batch CLI (`converter.py`)

```bash
python converter.py <unity_project_path> <output_dir> [OPTIONS]
```

Runs the full pipeline without stopping. Use this for automation, CI/CD, or
when you're confident the defaults are fine.

### Arguments

| Argument | Description |
|---|---|
| `unity_project_path` | Path to the root of your Unity project (must contain an `Assets/` folder) |
| `output_dir` | Directory where `converted_place.rbxl` and `conversion_report.json` will be written |

### Options

| Flag | Default | Description |
|---|---|---|
| `--api-key KEY` | `$ANTHROPIC_API_KEY` | Anthropic API key (**required** for C# → Luau transpilation) |
| `--verbose` / `--no-verbose` | `True` | Include per-script detail in the JSON report |
| `--roblox-api-key KEY` | `$ROBLOX_API_KEY` | Roblox Open Cloud API key (**required** for portal upload) |
| `--universe-id ID` | — | Roblox universe (experience) ID for upload |
| `--place-id ID` | — | Roblox place ID for upload |
| `--decimate` / `--no-decimate` | `True` | Conservative mesh decimation for Roblox polygon limits |

### Examples

```bash
# Using environment variable
ANTHROPIC_API_KEY=sk-ant-... python converter.py ./MyUnityProject ./roblox_output

# Specify API key inline
python converter.py ./MyUnityProject ./roblox_output --api-key sk-ant-...

# Upload to Roblox (requires Open Cloud API key)
python converter.py ./MyUnityProject ./roblox_output \
    --roblox-api-key YOUR_ROBLOX_KEY \
    --universe-id 123456 \
    --place-id 789012
```

### Output

```
roblox_output/
├── converted_place.rbxl          ← Open in Roblox Studio
├── converted_place_binary.rbxl   ← Binary format (generated during upload for Open Cloud)
├── scripts/                      ← Transpiled Luau scripts (standalone copies for reference/editing)
├── meshes/                       ← Decimated meshes (when --decimate is on)
├── asset_id_map.json             ← Cached Roblox asset IDs from upload
├── .convert_state.json           ← Interactive conversion state (resume support)
└── conversion_report.json        ← Full conversion summary
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
