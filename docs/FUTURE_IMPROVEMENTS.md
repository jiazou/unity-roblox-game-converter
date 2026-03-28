# Future Improvements

## Quick Wins

### ~~QW-1. Conversion report with warnings for silently dropped components~~ — DONE

**Resolution:** `conversion_helpers.py` now collects `ComponentWarning` objects during `node_to_part()` for every unrecognized component type. Each warning includes the GameObject name, component type, and an actionable suggestion from `_COMPONENT_SUGGESTIONS`. The report includes per-type counts and suggestions. The conversion report's `components` section shows `total_encountered`, `converted`, `dropped`, `dropped_by_type`, and `dropped_details`.

### QW-2. Transpiler warnings for networking attributes and object pooling (high impact)

**Problem:** Networking attributes (`[Command]`, `[ClientRpc]`, `[SyncVar]`) are detected for script classification but not converted to RemoteEvent/RemoteFunction patterns. Object pooling structures require manual refactoring. Users don't know these patterns need follow-up work.

**Fix:** During AI transpilation post-processing, detect and flag:
- Networking attributes — warn that multiplayer logic needs RemoteEvent/RemoteFunction wiring
- Object pooling patterns — warn that structural pool management needs manual review

**Files affected:** `modules/code_transpiler.py` (detection + warning collection), transpilation result struct (add warnings field)

## Medium Builds

### MB-1. Sprite extraction from spritesheets for UI (medium impact)

**Problem:** UI Image components reference sprites by GUID, but the pipeline doesn't extract individual sprites from spritesheets (atlas textures). UI buttons, icons, and HUD elements appear blank in the converted game.

**Fix:**
- Parse `.meta` files for sprites to get atlas rect coordinates
- Slice individual sprites from spritesheets during asset extraction
- Upload sliced sprites as individual Decal assets
- Wire sprite asset IDs into ScreenGui ImageLabel Image properties

**Files affected:** `modules/asset_extractor.py` (sprite slicing), `modules/ui_translator.py` (sprite GUID → asset ID wiring), `modules/roblox_uploader.py` (sprite upload)

### MB-2. Terrain heightmap → Roblox Terrain conversion (high impact)

**Problem:** Unity Terrain (classID 218) is recognized but completely dropped. Games with terrain lose their entire landscape — no geometry, no texture, no collision.

**Fix:**
- Extract heightmap data from Unity terrain asset (raw float array)
- Extract splat/alpha maps for terrain layer blending
- Map Unity terrain layers to Roblox terrain materials (Grass, Sand, Rock, etc.)
- Generate Roblox Terrain voxel data via `Terrain:FillRegion()` in a loader script
- Handle terrain trees/detail objects as separate Part instances

**Files affected:** New `modules/terrain_converter.py`, `modules/rbxl_writer.py` (Terrain instance), loader script generation

### MB-3. Layout group support for UI (medium impact)

**Problem:** Unity's `HorizontalLayoutGroup`, `VerticalLayoutGroup`, and `GridLayoutGroup` components are ignored. Complex UI layouts that rely on auto-layout break in Roblox.

**Fix:**
- Map `HorizontalLayoutGroup` → `UIListLayout` with `FillDirection = Horizontal`
- Map `VerticalLayoutGroup` → `UIListLayout` with `FillDirection = Vertical`
- Map `GridLayoutGroup` → `UIGridLayout`
- Convert padding, spacing, and child alignment properties

**Files affected:** `modules/ui_translator.py`

## Hard / Architectural

### HA-1. Multi-material mesh splitting (high impact)

**Problem:** Roblox allows only 1 material per MeshPart. Unity meshes commonly have multiple sub-meshes with different materials (e.g., a character with separate body/clothes/skin materials). The converter uses only the first material and silently drops the rest.

**Fix:**
- During mesh processing, detect multi-material meshes (multiple material slots in MeshRenderer)
- Split the mesh into separate sub-meshes per material using trimesh or assimp
- Export each sub-mesh as a separate MeshPart
- Group sub-meshes under a Model to preserve hierarchy
- Apply correct material to each sub-mesh

**Files affected:** `modules/mesh_decimator.py` (mesh splitting), `modules/conversion_helpers.py` (multi-part assembly), `modules/rbxl_writer.py` (Model grouping)

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

Runtime Luau module consuming config tables from Phase 1. Follows the pattern of `bridge/StateMachine.lua` and `bridge/MonoBehaviour.lua`:
- `AnimatorBridge.new(humanoidOrAnimController, config)` — loads tracks, initializes parameters
- `:SetFloat(name, value)`, `:SetBool(name, value)`, `:SetTrigger(name)` — parameter API
- `:Update(dt)` — evaluates transition conditions, fires crossfades, updates blend tree weights

Scalability:
- Single shared Heartbeat connection batching all AnimatorBridge instances (not one per entity)
- Lazy `AnimationTrack` loading (only `:LoadAnimation()` on first state entry)
- Blend tree weights as sorted threshold lookup, not per-frame recalculation

Hardening:
- Config validated at construction time, not at runtime
- Unknown parameters → `warn()` once, then ignore
- Missing clips → skip with warning, don't crash the state machine

**Phase 3 — Animation upload**

*Option A (default)* — KeyframeSequence in .rbxl: Generate `KeyframeSequence` XML nodes in `rbxl_writer.py`, parented under `AnimationController`. User publishes from Studio.

*Option B (enhanced)* — Roblox Animation API: Bulk-upload via `roblox_uploader.py` (same pattern as mesh/texture upload) and get back asset IDs for config tables.

**Phase 4 — Pipeline integration**

Wire into the existing pipeline between mesh decimation and bootstrap generation:
```
Processing phase:
  animation_converter.convert_animations(parsed_scenes, guid_index, anim_assets)
  → AnimationConversionResult:
      config_modules: list[RbxScriptEntry]   # ModuleScripts with config tables
      bridge_needed: bool                     # whether to include AnimatorBridge.lua
      warnings: list[str]                     # unconverted blend trees, missing clips
```

For `convert_interactive.py`: new `animations` sub-command between `transpile` and `assemble`, with a review decision point for flagged animations (complex blend trees, unmapped bones).

**Phase 5 — Update API mappings & transpiler**

Replace stub mappings in `api_mappings.py`:
```python
"Animator.SetBool": "animatorBridge:SetBool",
"Animator.SetFloat": "animatorBridge:SetFloat",
"Animator.SetTrigger": "animatorBridge:SetTrigger",
"Animator.Play": "animatorBridge:Play",
```

Add transpiler prompt rule: "If the script references an Animator, assume `animatorBridge` is passed via config."

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

#### Suggested Implementation Order

1. Config table generation + AnimatorBridge.lua (simple transitions, no blend trees) — covers ~60% of games
2. 1D blend trees — covers locomotion, the most common use case
3. KeyframeSequence export in rbxl_writer — makes output fully self-contained
4. Root motion, layers, 2D blend trees — advanced cases, diminishing returns

#### Open-Source Dependencies

| Tool | Role | Integration point |
|------|------|-------------------|
| `unityparser` (PyPI) | Parse Force Text `.anim` / `.controller` YAML | `animation_converter.py` |
| `UnityPy` (PyPI) | Parse binary Unity assets (fallback for non-text mode) | `animation_converter.py` |
| `RobloxStateMachine` (Wally, prooheckcp) | Reference for state machine patterns | Inspiration for `AnimatorBridge.lua` |
| `Arch` (Wally, bohraz) | Hierarchical state machine with sub-states | Reference for nested Mecanim sub-state machines |
| `FBX2glTF` (Meta, CLI) | FBX → glTF with baked animations | Optional pre-processing for animation extraction |
| `pygltflib` (PyPI) | Read/write glTF animation data | Alternative extraction path |

**Files affected:** New `modules/animation_converter.py`, new `bridge/AnimatorBridge.lua`, `modules/rbxl_writer.py` (AnimationController + KeyframeSequence instances), `modules/api_mappings.py` (updated animation mappings), `modules/code_transpiler.py` (prompt update), `modules/conversion_helpers.py` (bootstrap wiring), `modules/unity_yaml_utils.py` (new classIDs), `converter.py` + `convert_interactive.py` (pipeline integration)

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
