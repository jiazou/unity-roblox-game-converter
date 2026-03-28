# Unity → Roblox Game Converter

## Overview

This is a multi-phase pipeline that converts Unity game projects into Roblox place files (.rbxl). It handles scene hierarchy, materials, C# → Luau transpilation, mesh decimation, and optional Roblox Cloud upload.

## Architecture

- `converter.py` — Full end-to-end CLI (non-interactive, runs all phases)
- `convert_interactive.py` — Phase-based CLI for the `/convert-unity` skill (interactive, one phase at a time)
- `config.py` — All configuration constants (paths, API keys, thresholds)
- `modules/` — Individual pipeline modules (22 modules; no cross-imports except `conversion_helpers` which imports data types from `rbxl_writer`)
- `bridge/` — Reusable Unity API shim modules in Luau (9 modules: AnimatorBridge, Coroutine, GameObjectUtil, Input, MonoBehaviour, Physics, StateMachine, Time, TransformAnimator). Not yet auto-injected into .rbxl — assembly integration is TODO.

### Pipeline Phases

1. **Discovery**: `scene_parser` + `prefab_parser` — parse .unity/.prefab YAML
2. **Inventory**: `asset_extractor` + `guid_resolver` — catalog assets, build GUID index
3. **Processing**: `material_mapper` + `code_transpiler` + `mesh_decimator` + `scriptable_object_converter` + `animation_converter` + `vertex_color_baker`
4. **Assembly**: `rbxl_writer` + `ui_translator` + `conversion_helpers` — build .rbxl XML, generate bootstrap
5. **Upload**: `roblox_uploader` + `report_generator` — upload assets, inject MeshLoader, patch asset IDs, upload to Roblox Cloud, generate report

### Key Design Principles

- Data flows linearly: each module's output is passed explicitly to the next
- No pipeline module imports another pipeline module — all wiring happens in the orchestrators (`converter.py`, `convert_interactive.py`). The exception is `conversion_helpers.py`, which imports data types from `rbxl_writer.py` to construct `RbxPartEntry` objects.
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

## Known Limitations

See `docs/UNSUPPORTED.md` for the full list. Key ones:
- Vertex colors require baking to textures via `vertex_color_baker.py` + assimp (Roblox ignores FBX vertex colors)
- One material per MeshPart (multi-material meshes need splitting)
- C# → Luau transpilation requires an Anthropic API key (Claude)
