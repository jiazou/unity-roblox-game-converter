# Future Improvements

## Quick Wins

### ~~QW-1. Conversion report with warnings for silently dropped components~~ — DONE

**Resolution:** `conversion_helpers.py` now collects `ComponentWarning` objects during `node_to_part()` for every unrecognized component type. Each warning includes the GameObject name, component type, and an actionable suggestion from `_COMPONENT_SUGGESTIONS`. The report includes per-type counts and suggestions. The conversion report's `components` section shows `total_encountered`, `converted`, `dropped`, `dropped_by_type`, and `dropped_details`.

### ~~QW-2. Transpiler warnings for networking attributes and object pooling~~ — DONE

**Resolution:** `_analyze_csharp_patterns()` now detects networking attributes (`[Command]`, `[ClientRpc]`, `[SyncVar]`, etc.) and object pooling patterns (`ObjectPool`, `PoolManager`, `Spawn/Despawn/Recycle`). Detected patterns are attached to `TranspiledScript.warnings` and surfaced in the interactive transpile phase output. Scripts with networking or pooling patterns have their confidence capped at 0.5, causing them to be flagged for manual review.

## Medium Builds

### ~~MB-1. Sprite extraction from spritesheets for UI (medium impact)~~ — DONE

**Resolution:** New `modules/sprite_extractor.py` parses `.meta` TextureImporter data for sprite rects (single and multi-sprite modes). Slices individual sprites from source textures using Pillow, handling Unity's bottom-left coordinate origin → Pillow top-left conversion. Writes extracted PNGs to `<output>/sprites/` which the existing `roblox_uploader.py` already picks up for upload. Wired into both `converter.py` (batch) and `convert_interactive.py` (assemble phase). Single-sprite textures map GUID → file directly; spritesheets use `guid:spritename` compound keys.

### ~~MB-2. Terrain heightmap → Roblox Terrain conversion (high impact)~~ — DONE

**Resolution:** New `modules/terrain_converter.py` parses Unity TerrainData binary `.asset` files to extract heightmap data (uint16 arrays), terrain dimensions, and terrain layer names from `.terrainlayer` files. Downsamples the heightmap to a configurable grid (default 65×65) and generates a `TerrainLoader` ServerScript that recreates terrain using `Terrain:FillBlock()` with elevation-based material assignment (Sand, Grass, Ground, Rock). Also generates water base. Handles Git LFS pointers with a clear warning message. Wired into `convert_interactive.py` assemble phase — auto-detects and converts terrain with no user intervention. Also saves `terrain_data.json` for optional MCP-based direct terrain painting in Roblox Studio. Remaining gap: splatmap-based per-layer material painting (currently uses elevation-only heuristic) and terrain trees/detail objects.

### ~~MB-3. Layout group support for UI (medium impact)~~ — DONE

**Resolution:** `_extract_layout_groups()` in `ui_translator.py` detects `HorizontalLayoutGroup`, `VerticalLayoutGroup`, and `GridLayoutGroup` components (including `UnityEngine.UI.` prefixed names). Maps them to `RobloxLayoutChild` dataclass objects: `HorizontalLayoutGroup` → `UIListLayout` with `FillDirection = Horizontal`, `VerticalLayoutGroup` → `UIListLayout` with `FillDirection = Vertical`, `GridLayoutGroup` → `UIGridLayout`. Converts spacing, cell size, cell padding, and child alignment (`m_ChildAlignment` enum → Roblox `HorizontalAlignment`/`VerticalAlignment`). `to_rbx_ui_element()` converts `RobloxLayoutChild` objects to dicts for `RbxUIElement.layout_children`. `_make_ui_element()` in `rbxl_writer.py` serializes layout children as XML child `<Item>` nodes with appropriate UDim/UDim2 properties.

## Hard / Architectural

### ~~HA-1. Multi-material mesh splitting (high impact)~~ — DONE

**Resolution:** New `modules/mesh_splitter.py` loads multi-material meshes via trimesh (with GLB/FBX scene preservation), extracts per-material geometries, and exports each as a separate OBJ. `_try_split_multi_material()` in `conversion_helpers.py` detects multi-material MeshRenderers, calls the splitter, and creates child `RbxPartEntry` objects (one per submesh) each with its own `SurfaceAppearance`. The parent part becomes a grouping Model via `rbxl_writer._is_grouping_node()`. Falls back gracefully to single-material behavior when trimesh can't split.

### HA-2. Animation retargeting — Animator → Roblox animations (high impact)

**Problem:** Unity's Animator component (classID 95) is recognized but not converted. Games with character animations, state machines, blend trees, and animation events lose all animation behavior.

**Strategy:** Embedded state machine generation (Strategy A). Parse Unity animation assets, generate Luau config tables describing the state machine, and pair them with a runtime `AnimatorBridge.lua` that drives Roblox `AnimationController`/`AnimationTrack`. All output is self-contained in the `.rbxl` — no external tools required at runtime.

**Status:** Phases 0–1 implemented in `modules/animation_converter.py` (66 tests). Parses `.controller` and `.anim` YAML, generates per-Animator Luau config tables, includes bone name mapping (Unity Humanoid → Roblox R15). `bridge/AnimatorBridge.lua` exists as the runtime consumer. Remaining: Phases 2–5 (animation upload, pipeline integration into convert_interactive.py, API mapping updates).

#### Implementation Phases

**Phase 0 — Expand Discovery** (scene_parser + asset_extractor) — DONE
- Add classID 91 (AnimatorController) and 74 (AnimationClip) to `unity_yaml_utils.py`
- Extract from Animator components: `m_Controller` GUID, `m_Avatar` GUID, `m_ApplyRootMotion`
- Parse `.controller` YAML → state machine graph (states, transitions, parameters, blend trees)
- Parse `.anim` YAML → keyframe curves (time, value, inTangent, outTangent per bone per property)
- Tool: `unityparser` (PyPI) for Force Text YAML, or `UnityPy` for binary assets

**Phase 1 — New module: `modules/animation_converter.py`** — DONE

Produces two outputs from parsed animation data:

*Output A — Animation config tables* (Luau ModuleScripts, one per Animator):
```lua
return {
    parameters = {
        speed = { type = "Float", default = 0 },
        isGrounded = { type = "Bool", default = true },
        attack = { type = "Trigger" },
    },
    states = {
        Idle = { clip = "rbxassetid://111", speed = 1, loop = true },
        Walk = { clip = "rbxassetid://222", speed = 1, loop = true },
    },
    transitions = {
        { from = "Idle", to = "Walk", conditions = {{ param = "speed", op = ">", value = 0.1 }} },
        { from = "Any", to = "Attack", conditions = {{ param = "attack", op = "trigger" }} },
    },
    blendTrees = {
        Locomotion = {
            param = "speed",
            clips = {
                { threshold = 0, clip = "rbxassetid://111" },
                { threshold = 1, clip = "rbxassetid://222" },
            },
        },
    },
    defaultState = "Idle",
}
```

Config generation is pure data transformation — deterministic, no AI needed, fully testable.

*Output B — Bone name mapping table*: Static lookup from Unity Humanoid bone names → Roblox R15 Motor6D names (~20 bones). Ships as a constant in the module.

**Phase 2 — New bridge: `bridge/AnimatorBridge.lua`**

Runtime Luau module consuming config tables from Phase 1. API: `AnimatorBridge.new(humanoidOrAnimController, config)`, `:SetFloat/SetBool/SetTrigger`, `:Update(dt)`.

**Phase 3 — Animation upload**

Generate `KeyframeSequence` XML nodes in `rbxl_writer.py` (option A), or bulk-upload via `roblox_uploader.py` to get asset IDs (option B).

**Phase 4 — Pipeline integration**

Wire `animation_converter.convert_animations()` into the pipeline between mesh decimation and bootstrap generation. Add `animations` sub-command to `convert_interactive.py`.

**Phase 5 — Update API mappings & transpiler**

Replace stub `Animator.*` mappings in `api_mappings.py` with `animatorBridge:*` calls. Add transpiler prompt rule for Animator references.

#### Difficulty Breakdown

| Component | Difficulty | Notes |
|-----------|-----------|-------|
| `.anim` YAML parsing | Low | Same tagged-YAML format we already parse; `unityparser` handles it |
| Config table generation | Low | Pure data transform, deterministic, fully testable |
| Bone name mapping (R15) | Low | ~20 fixed bone pairs, one-time lookup table |
| AnimatorBridge.lua (simple transitions) | Medium | State machine + crossfade is well-defined; `bridge/StateMachine.lua` is 80% there |
| 1D blend trees | Medium | Linear interpolation between thresholds |
| `.controller` state graph parsing | Medium-High | Mecanim serialized format is nested; transitions have interruption rules |
| 2D blend trees (freeform) | High | Cartesian/directional blending needs Delaunay triangulation |
| Animation layers + avatar masks | High | No Roblox per-bone masking; needs per-bone track splitting or `AnimationTrack.Priority` |
| Root motion extraction | High | Separate root bone curves → apply as HumanoidRootPart movement |
| Inverse kinematics | Not feasible | Would require a full IK solver in Luau — out of scope |

#### Implementation Order

1. Config table generation + AnimatorBridge.lua (simple transitions) — covers ~60% of games
2. 1D blend trees — covers locomotion
3. KeyframeSequence export — makes output self-contained
4. Root motion, layers, 2D blend trees — advanced cases

### HA-3. NavMesh → Roblox pathfinding (medium impact)

**Problem:** Unity's NavMeshAgent (classID 195) is recognized but not converted. Games with AI navigation have broken enemy/NPC movement.

**Fix:**
- Extract baked NavMesh data from Unity project
- Convert NavMesh geometry to Roblox PathfindingService-compatible navigation
- Map NavMeshAgent properties (speed, acceleration, stopping distance) to Humanoid:MoveTo() parameters
- Generate pathfinding Luau scripts that use PathfindingService

**Files affected:** New `modules/navmesh_converter.py`, script generation for AI agents

## Infrastructure / Pipeline

### IP-1. Upload-then-patch anti-pattern (high impact)

**Problem:** Every pipeline run re-uploads all assets, and the .rbxl patching logic has grown to 4+ strategies of regex/XML matching accumulated over debugging sessions.

**Fix:** Separate asset upload from place assembly:
- Upload phase produces an **asset manifest** (`{filename: asset_id, content_hash: ...}`)
- Assembly phase reads the manifest and builds the .rbxl directly with correct asset IDs
- No post-hoc patching needed
- Manifest is persistent — only upload new/changed assets

**Files affected:** `modules/roblox_uploader.py` (patching logic), `convert_interactive.py` (upload command)

### IP-2. Monolithic roblox_uploader.py (1456 lines doing 6 jobs)

**Problem:** One file handles FBX→GLB conversion, texture injection, API uploading, .rbxl XML patching (4 strategies), Unity YAML parsing for mesh→material mapping, MeshLoader script generation, and username resolution.

**Fix:** Split into focused modules:
- `modules/asset_converter.py` — FBX→GLB, texture injection into glTF
- `modules/asset_uploader.py` — Open Cloud upload, async polling, caching
- `modules/rbxl_patcher.py` — XML patching strategies (if still needed after IP-1)
- `modules/mesh_loader_generator.py` — Luau MeshLoader script generation
- Keep `modules/roblox_uploader.py` as thin orchestrator

### IP-3. Content-hash deduplication for uploads

**Problem:** 175 meshes × ~3 seconds each = 9+ minutes of API calls per run. No content hashing means identical assets get re-uploaded.

**Status:** Partially addressed — asset cache (`asset_id_map.json`) now skips re-uploads by filename. Missing: content-hash-based deduplication (same content, different filename still re-uploads).

**Fix:**
- Hash each GLB/PNG/OGG file (SHA-256)
- Store `{content_hash: roblox_asset_id}` in the asset cache
- Before uploading, check if hash already exists → skip upload, reuse asset ID

**Files affected:** `modules/roblox_uploader.py` (upload loops, cache format)

### IP-4. Custom serializer vs rbx-dom/rbxmk (low priority)

**Problem:** `rbxl_binary_writer.py` reimplements Roblox's binary format. The research says rbx-dom is "the definitive industry standard." Our serializer misses internal properties (confirmed: MeshPart.MeshId set in XML is ignored by Studio).

**Current workaround:** InsertService:LoadAsset() at runtime bypasses the serializer for meshes entirely. The serializer only handles simple properties (scripts, lighting, spawn points) which it does correctly.

**Why low priority:** Since meshes load via InsertService, the serializer only writes the place shell. For that use case it works fine. Replacing with rbxmk adds a Go binary dependency for marginal benefit.

### ~~IP-5. Replace rule-based C# transpiler~~ — DONE

**Resolution:** Rule-based and AST transpilers have been removed. All C# → Luau transpilation now uses Claude AI exclusively. The architectural gap (MonoBehaviour lifecycle, component queries, Addressables) is handled by the AI using the Unity Bridge API as vocabulary context.
