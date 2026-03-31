# Unity → Roblox Game Converter

## Overview

This is a multi-phase pipeline that converts Unity game projects into Roblox place files (.rbxl). It handles scene hierarchy, materials, C# → Luau transpilation, mesh decimation, and optional Roblox Cloud upload.

## Architecture

- `converter.py` — Full end-to-end CLI (non-interactive, runs all phases)
- `convert_interactive.py` — Phase-based CLI for the `/convert-unity` skill (interactive, one phase at a time)
- `config.py` — All configuration constants (paths, API keys, thresholds)
- `modules/` — Individual pipeline modules (21 modules + `__init__.py`). `conversion_helpers` imports multiple pipeline modules (`scene_parser`, `prefab_parser`, `material_mapper`, `code_transpiler`, `guid_resolver`, `mesh_decimator`, `report_generator`, `rbxl_writer`) for data composition.
- `bridge/` — Reusable Unity API shim modules in Luau (9 modules: AnimatorBridge, Coroutine, GameObjectUtil, Input, MonoBehaviour, Physics, StateMachine, Time, TransformAnimator). All modules are auto-injected: AnimatorBridge and TransformAnimator by `animation_converter.py` when animation components are detected; the other 7 by `bridge_injector.py` which scans transpiled Luau for require() calls and API usage patterns.

### Pipeline Phases

1. **Discovery**: `scene_parser` + `prefab_parser` — parse .unity/.prefab YAML
2. **Inventory**: `asset_extractor` + `guid_resolver` — catalog assets, build GUID index
3. **Processing**: `material_mapper` + `code_transpiler` + `code_validator` + `mesh_decimator` + `scriptable_object_converter` + `animation_converter` + `vertex_color_baker`
4. **Assembly**: `rbxl_writer` + `ui_translator` + `conversion_helpers` — build .rbxl XML, generate bootstrap
5. **Upload**: `roblox_uploader` + `report_generator` — upload assets, inject MeshLoader, patch asset IDs, upload to Roblox Cloud, generate report

### Key Design Principles

- Data flows linearly: each module's output is passed explicitly to the next
- No pipeline module imports another pipeline module — all wiring happens in the orchestrators (`converter.py`, `convert_interactive.py`). The exception is `conversion_helpers.py`, which imports multiple pipeline modules for data composition.
- State between interactive phases is stored in `<output_dir>/.convert_state.json`
- Roblox Studio ignores `MeshPart.MeshId` set in XML — mesh assets must be loaded at runtime via `InsertService:LoadAsset()`. The upload phase injects a `MeshLoader` server Script that handles this.

## Dependencies

Python packages: see `requirements.txt` (`trimesh`, `Pillow`, `numpy`, `pyassimp`, etc.)

System libraries:
- **assimp** (`brew install assimp`) — Required for FBX vertex color baking. The `pyassimp` Python wrapper needs `libassimp.dylib` at `/opt/homebrew/lib/`. Without it, vertex-colored meshes (VCOL material) render as flat gray in Roblox.

## Running Tests

```bash
python -m pytest tests/ -v
```

## Skills

The `/convert-unity` skill (`.claude/skills/convert-unity.md`) provides an interactive conversion experience, pausing at decision points for human input:
- Scene selection when multiple scenes exist
- Material conversion review for unconvertible/partial materials
- Code transpilation review for flagged (low-confidence) scripts
- Mesh decimation confirmation
- Upload configuration

## Bug Fix Protocol

When a problem is found in converted output (e.g., the Trash Dash Roblox game), always fix **both**:

1. **Fix the converter/skill first** — update the pipeline code (`modules/`), converter skill (`.claude/skills/convert-unity/SKILL.md`), or bridge modules (`bridge/`) so future conversions produce correct output.
2. **Then fix the current output** — update the game scripts in the output directory (e.g., `trash-dash-roblox-v7/scripts/`) so the already-converted game works.

Never do one without the other. A fix only to the output will regress on the next conversion. A fix only to the converter leaves the current game broken.

## Known Limitations

See `docs/UNSUPPORTED.md` for the full list. Key ones:
- Vertex colors require baking to textures via `vertex_color_baker.py` + assimp (Roblox ignores FBX vertex colors)
- One material per MeshPart (multi-material meshes need splitting)
- C# → Luau transpilation requires an Anthropic API key (Claude)
