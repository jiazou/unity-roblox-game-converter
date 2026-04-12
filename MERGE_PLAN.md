# Merge Plan: unity-roblox-game-converter → unity2rbxlx

## Goal

Merge the `unity-roblox-game-converter` repo (hereafter **"source"**) into the `unity2rbxlx` repo (hereafter **"dest"**). The dest repo is the surviving codebase. The final result has two modes:

1. **Claude Code Skill** (`/convert-unity`) — interactive, phase-by-phase conversion with human decision points at each stage. Powered by `convert_interactive.py` and the `.claude/skills/convert-unity/` skill definition.
2. **CLI Tool** (`u2r.py`) — fully automated, runs all pipeline phases end-to-end. Existing in the dest repo today.

---

## Repo Comparison Summary

### Architecture

| Aspect | Source (unity-roblox-game-converter) | Dest (unity2rbxlx) |
|---|---|---|
| Structure | Flat: `modules/`, `bridge/`, `tests/` | Organized package: `core/`, `unity/`, `converter/`, `roblox/`, `runtime/`, `comparison/`, `utils/`, `tools/` |
| Entry points | `converter.py` (batch) + `convert_interactive.py` (interactive skill) | `u2r.py` (Click CLI: convert, analyze, validate, resolve, compare, publish) |
| Type system | Ad-hoc dataclasses per module | Centralized: `core/unity_types.py`, `core/roblox_types.py` (RbxPlace, RbxPart, etc.) |
| State management | `.convert_state.json` for interactive mode | `ConversionContext` — rich, JSON-serializable, tracks mesh resolution, uploads, stats |
| Pipeline | Linear wiring in orchestrator scripts | `Pipeline` class with named phases, resume, multi-scene support |
| Coordinate system | Inline transforms in conversion_helpers | Dedicated `core/coordinate_system.py` with FBX pre-rotation handling |

### What the Dest Repo Already Has (keep as-is)

- `core/conversion_context.py` — rich mutable state
- `core/roblox_types.py` — comprehensive typed output (RbxPlace, RbxPart, RbxScript, RbxTerrain, etc.)
- `core/unity_types.py` — typed input (SceneNode, ParsedScene, GuidIndex, etc.)
- `core/coordinate_system.py` — coordinate transforms with FBX pre-rotation
- `converter/pipeline.py` — orchestrator with resume + multi-scene
- `converter/component_converter.py` — 50+ Unity component types
- `converter/scene_converter.py` — recursive scene-to-RbxPlace conversion
- `converter/script_coherence.py` — cross-script consistency
- `converter/fps_client_generator.py` — auto FPS client controller
- `converter/stub_generator.py` — Luau stubs for failed transpilations
- `converter/script_asset_rewriter.py` — rewrite script asset refs
- `roblox/luau_place_builder.py` — headless mesh resolution via Luau Execution API
- `roblox/studio_bridge.py` + studio_launcher + studio_resolver — Studio integration
- `roblox/terrain_encoder.py` — SmoothGrid binary terrain encoding
- `roblox/experience_manager.py` — universe/place management
- `comparison/` — visual diff, state dumping, input recording/replay
- `tools/transform_audit.py` — coordinate transform validation
- `unity/binary_scene_parser.py` — binary .unity via UnityPy
- `unity/script_analyzer.py` — C# script classification
- CLI subcommands: analyze, validate, resolve, compare, publish

### What the Source Repo Has That Must Be Ported

#### New Modules (no equivalent in dest)

| Source Module | Proposed Dest Location | Purpose |
|---|---|---|
| `modules/bridge_injector.py` | `converter/converter/bridge_injector.py` | Auto-detect Unity API usage in transpiled Luau, inject bridge shims |
| `modules/vertex_color_baker.py` | `converter/converter/vertex_color_baker.py` | Bake mesh vertex colors to textures (Roblox ignores FBX vertex colors) |
| `modules/sprite_extractor.py` | `converter/converter/sprite_extractor.py` | Extract sprites from spritesheets via .meta TextureImporter data |
| `modules/mesh_splitter.py` | `converter/converter/mesh_splitter.py` | Split multi-material meshes (Roblox: 1 material per MeshPart) |
| `modules/scriptable_object_converter.py` | `converter/converter/scriptable_object_converter.py` | Convert .asset ScriptableObjects → Luau data tables |
| `modules/rbxl_binary_writer.py` | `converter/roblox/rbxl_binary_writer.py` | XML .rbxlx → binary .rbxl (required for Open Cloud Place API) |
| `modules/report_generator.py` | `converter/converter/report_generator.py` | Generate JSON conversion report |
| `modules/code_validator.py` | Merge into `converter/converter/luau_validator.py` | Luau syntax validation (complement dest's richer validator) |
| `modules/unity_yaml_utils.py` | Merge into `converter/unity/yaml_parser.py` | YAML parsing utilities (compare for unique helpers) |
| `convert_interactive.py` | `converter/convert_interactive.py` | Interactive phase-based CLI for skill |
| `modules/conversion_helpers.py` | Split across dest modules | Large orchestration module — see decomposition plan below |

#### Bridge/Runtime Luau Files

The two repos have **complementary** runtime Luau modules. Both sets should coexist.

| Source (`bridge/`) | Dest (`runtime/`) | Status |
|---|---|---|
| `Input.lua` | — | **Port** (rename to `.luau`) |
| `Time.lua` | — | **Port** |
| `MonoBehaviour.lua` | — | **Port** |
| `Coroutine.lua` | — | **Port** |
| `GameObjectUtil.lua` | — | **Port** |
| `StateMachine.lua` | — | **Port** |
| `TransformAnimator.lua` | — | **Port** |
| `AnimatorBridge.lua` | `animator_runtime.luau` | **Reconcile** — different animation approaches |
| `Physics.lua` | `physics_bridge.luau` | **Reconcile** — different API surfaces |
| — | `cinemachine_runtime.luau` | Keep (dest only) |
| — | `event_system.luau` | Keep (dest only) |
| — | `nav_mesh_runtime.luau` | Keep (dest only) |
| — | `pickup_runtime.luau` | Keep (dest only) |
| — | `sub_emitter_runtime.luau` | Keep (dest only) |

#### Skill Definition & Interactive Mode

| Source | Dest | Purpose |
|---|---|---|
| `.claude/skills/convert-unity/SKILL.md` | `converter/.claude/skills/convert-unity/SKILL.md` | Claude Code skill definition |
| `.claude/skills/convert-unity/references/upload-patching.md` | Same, ported | Game logic porting guidance |
| `.claude/skills/review-csharp-lua-conversion/` | Archived — skip | Already marked archived in source |

#### Tests

| Source Test File | Dest Location | Notes |
|---|---|---|
| `tests/test_bridge_injector.py` | `converter/tests/test_bridge_injector.py` | New |
| `tests/test_vertex_color_baker.py` | `converter/tests/test_vertex_color_baker.py` | New |
| `tests/test_sprite_extractor.py` | `converter/tests/test_sprite_extractor.py` | New |
| `tests/test_mesh_splitter.py` | `converter/tests/test_mesh_splitter.py` | New |
| `tests/test_scriptable_object_converter.py` | `converter/tests/test_scriptable_object_converter.py` | New |
| `tests/test_report_generator.py` | `converter/tests/test_report_generator.py` | New |
| `tests/test_code_validator.py` | Merge into existing validator tests | Complement |
| Shared module tests (scene_parser, material_mapper, etc.) | Merge unique test cases | Take union |

#### Documentation

| Source Doc | Action |
|---|---|
| `docs/UNSUPPORTED.md` | Port to dest |
| `docs/GAME_LOGIC_PORTING.md` | Port to dest |
| `docs/KNOWN_ISSUES.md` | Merge with dest's known limitations |
| `docs/MODULE_STATUS.md` | Rewrite for merged module set |
| `CLAUDE.md` | Rewrite for merged architecture |
| `README.md` | Rewrite with two-mode documentation |

### Shared Modules (exist in both — need reconciliation)

| Module Area | Source | Dest | Resolution Strategy |
|---|---|---|---|
| API mappings | `modules/api_mappings.py` | `converter/converter/api_mappings.py` | Union of both mapping tables |
| Material mapper | `modules/material_mapper.py` | `converter/converter/material_mapper.py` | Dest is more mature; port missing shader support from source |
| Code transpiler | `modules/code_transpiler.py` | `converter/converter/code_transpiler.py` | Dest has dual rule-based+AI; source is AI-only. Keep dest's, port better prompt engineering |
| Scene parser | `modules/scene_parser.py` | `converter/unity/scene_parser.py` | Dest also has binary parsing. Keep dest's, check for edge cases |
| Prefab parser | `modules/prefab_parser.py` | `converter/unity/prefab_parser.py` | Dest has variant support. Keep dest's |
| GUID resolver | `modules/guid_resolver.py` | `converter/unity/guid_resolver.py` | Both robust. Keep dest's |
| Asset extractor | `modules/asset_extractor.py` | `converter/unity/asset_extractor.py` | Keep dest's |
| Animation converter | `modules/animation_converter.py` | `converter/converter/animation_converter.py` | Source has root motion + blend tree. Compare and merge |
| Mesh decimator | `modules/mesh_decimator.py` | `converter/converter/mesh_processor.py` | Dest uses same approach. Keep dest's |
| Terrain converter | `modules/terrain_converter.py` | `converter/converter/terrain_converter.py` | Dest has SmoothGrid binary. Keep dest's |
| UI translator | `modules/ui_translator.py` | `converter/converter/ui_translator.py` | Compare; port missing element types |
| rbxl writer | `modules/rbxl_writer.py` | `converter/roblox/rbxlx_writer.py` | Keep dest's; port binary writer as new module |
| Uploader | `modules/roblox_uploader.py` | `converter/roblox/cloud_api.py` | Keep dest's (has Luau Execution API) |
| LLM cache | `modules/llm_cache.py` | `converter/utils/llm_cache.py` | Compare; keep more robust |
| Retry | `modules/retry.py` | `converter/utils/retry.py` | Keep dest's |
| Luau validator | `modules/code_validator.py` | `converter/converter/luau_validator.py` | Dest's is far richer (6950 LOC, 50+ categories). Port unique patterns from source |

### Decomposing `conversion_helpers.py`

The source's `conversion_helpers.py` (2087 LOC) is a large module that handles orchestration logic. In the dest repo, this is already decomposed:

| Source Function | Dest Equivalent |
|---|---|
| `scene_nodes_to_parts()` | `converter/scene_converter.py` |
| `node_to_part()` | `converter/scene_converter.py` + `converter/component_converter.py` |
| `apply_collider_properties()` | `converter/component_converter.py:convert_collider()` |
| `convert_light_components()` | `converter/component_converter.py:convert_light()` |
| `convert_audio_components()` | `converter/component_converter.py:convert_audio()` |
| `generate_bootstrap_script()` | Not in dest — **port** |
| `resolve_prefab_instances()` | `converter/scene_converter.py` (already handles) |
| `extract_serialized_field_refs()` | Not in dest — **port** |
| `generate_prefab_packages()` | Not in dest — **port** |
| `build_report()` | Port via `report_generator.py` |
| `transpiled_to_rbx_scripts()` | `converter/scene_converter.py` (already handles) |

---

## Implementation Phases

### Phase 0: Documentation & Planning (THIS DOCUMENT)

- [x] Analyze both repos
- [x] Map module equivalences
- [ ] Refine plan with team feedback
- [ ] Finalize implementation order

### Phase 1: Two-Mode Entry Points & Documentation ✅

**Status:** Complete (branch `merge-converters`, merged).

Delivered: `convert_interactive.py` (Click CLI with 10 subcommands), `.claude/skills/convert-unity/` skill definition with per-phase reference docs, README/CLAUDE.md/ARCHITECTURE.md updates.

**Post-merge fixes applied:** R1 (_run_through replays upload/resolve), R3 (upload ignores .roblox_ids.json), R4 (--api-key doesn't reach transpiler), C6 (failed upload marked as success), C7 (preflight Python/package checks wrong).

### Phase 2: Port New Standalone Modules ✅

**Status:** Complete (branch `merge-converters-phase2`, merged).

Delivered: All 7 standalone Python modules ported (bridge_injector, vertex_color_baker, sprite_extractor, mesh_splitter, scriptable_object_converter, rbxl_binary_writer, report_generator), 9 bridge Luau files ported to `runtime/` (.lua → .luau, Physics.lua → physics_queries.luau, AnimatorBridge.lua → animator_bridge.luau), config.py updated.

**Post-merge fixes applied (86392e6):**
- assemble `--retranspile` flag: skip transpilation when already completed to preserve hand-edited Luau
- pipeline.write_output: rehydrate scripts from disk when transpilation was skipped
- upload: added `write_output` to rebuild phase list (was missing scripts)
- Scene paths: project-relative paths instead of basename-only for disambiguation
- Cross-project contamination guard: hard-fail when persisted context comes from a different Unity project

### Phase 3: Integrate New Modules into Pipeline

**Goal:** Wire the Phase 2 modules into the existing `Pipeline` class. All integrations must work in three flows: (a) full `u2r.py` CLI, (b) interactive `assemble` with fresh transpilation, (c) interactive `assemble` with `--retranspile=false` (script rehydration path). The `upload` command's rebuild path (`parse → … → write_output`) must also include every new step.

> **Key lesson from Phase 1-2:** `PipelineState` does not survive across interactive commands. Any feature that only populates in-memory state will disappear on preserved-script assemble and upload rebuild. Features must either persist artifacts to disk or integrate into `write_output` where both the fresh-transpile and rehydration paths converge.

1. **Add bridge injection** inside `write_output`, after scripts are populated in `rbx_place`
   - Must run after both the fresh-transpile path AND the disk-rehydration path (pipeline.py ~L934)
   - Scan `self.state.rbx_place.scripts` for API patterns, inject matching runtime modules
   - Dedupe against existing `RbxScript.name` entries to avoid double-injection (bridge_injector dedupes by filename, but RbxScript uses basename-only names)
   - Place near existing require-injection/reclassification/runtime-injection logic (~L1023)

2. **Add vertex color baking** after `convert_materials`, before `convert_scene`
   - ~~Original plan said "between convert_materials and upload_assets"~~ — actual phase order has `upload_assets` before `convert_materials`, so that placement was impossible
   - After materials mapped, bake vertex colors for meshes that need it
   - Reads `uses_vertex_colors` flag from `MaterialMapping` (added in Phase 4.2)

3. **Add sprite extraction** to `extract_assets`
   - Scan .meta files for spritesheet TextureImporters
   - No interactive-mode complications (extract_assets always runs)

4. **Add mesh splitting** to `convert_scene`
   - When MeshRenderer has `len(m_Materials) > 1`, split before creating RbxParts
   - No interactive-mode complications (convert_scene always runs in assemble)

5. **Add scriptable object conversion** to `transpile_scripts` AND persist to disk
   - Generate ModuleScript data tables from .asset files during transpilation
   - **Critical:** Also persist generated `.luau` files to `scripts/` on disk, so `write_output`'s rehydration path picks them up when transpilation is skipped
   - Alternative: run as a separate sub-step in `write_output` that generates from source .asset files regardless of transpile state

6. **Add binary writer** as optional post-`write_output` step
   - Convert .rbxlx → .rbxl after the place file is written
   - **Do NOT wire into the interactive `upload` command** — upload rebuilds `rbx_place` in-memory and uses `execute_luau`, not file upload. Binary writing only matters for direct Open Cloud place-upload (future capability in `cloud_api.py`)

7. **Replace inline report generation** in `write_output` and `convert_interactive.py:report()`
   - The ported `report_generator.py` should replace the existing ad hoc JSON writers in pipeline.py (~L1500) and convert_interactive.py:report(), not add a third reporting path
   - Must use project-relative scene paths (not basename-only)

8. **Port `generate_bootstrap_script()`** from conversion_helpers
   - Generates GameBootstrap.lua lifecycle script
   - Must integrate into `write_output` (depends on final `rbx_place.scripts` set)

9. **Port `extract_serialized_field_refs()`** from conversion_helpers
   - Finds MonoBehaviour fields referencing assets
   - Can run before `write_output`, but results consumed by script/package generation must be persisted to `conversion_context.json` (not left only in `PipelineState`)

10. **Port `generate_prefab_packages()`** from conversion_helpers
    - Creates per-prefab packages for ReplicatedStorage/Templates
    - Must persist package metadata to disk or integrate into `write_output`, so upload rebuilds and preserved-script assemble runs don't diverge

11. **Extend `write_output` disk rewrite to handle new subdirectories**
    - Current rewrite only handles `scripts/` and `scripts/animations/`
    - Must also handle `animation_data/`, `packages/`, and ScriptableObject module paths added by this phase and Phase 4

12. **Add script metadata persistence**
    - Current rehydration infers script type heuristically from content (pipeline.py ~L942) and uses only the file stem (~L941), losing directory identity
    - Add a `script_manifest.json` (or extend `conversion_context.json`) that records `{filename, script_type, parent_path}` at transpilation time, so rehydration is lossless
    - All new Phase 3/4 generated scripts must follow this same project-identity pattern (matching the cross-project guard precedent from the Phase 2 fix)

### Phase 4: Reconcile Shared Modules

**Goal:** For modules in both repos, take the best of both. **See [MERGE_PLAN_PHASE4.md](MERGE_PLAN_PHASE4.md) for the detailed plan** with per-module diffs, step-by-step actions, acceptance criteria, and execution order.

> **Key lesson from Phase 1-2:** Interactive mode can skip `transpile_scripts` entirely. Any reconciliation work that only populates `PipelineState` or `state.transpilation_result` will be invisible to the preserved-script assemble and upload rebuild paths. Reconciled modules must persist their outputs or integrate at `write_output` time.

Summary:

1. **api_mappings** (Low) — union merge of mapping tables, dedup. Dest is superset; port source-only entries.
2. **material_mapper** (High) — port 14+ missing shaders, 6 missing texture ops, unconverted feature tracking, vertex color detection into dest's cleaner type system. **Added criterion:** Must be idempotent under interactive prerequisite replay — companion scripts, UNCONVERTED.md, and vertex-color outputs must not assume upload/resolve already ran.
3. **code_transpiler** (Medium) — port dependency-aware context building (topological sort + dependency Luau injection) and C# pattern analysis warnings into dest's concurrent dual-strategy transpiler. **Added criterion:** Dependency ordering and warnings must be persisted (via script manifest or conversion_context.json) so the preserved-script path doesn't lose them.
4. **luau_validator** (Low) — port `check_method_completeness()` and verify comment/string stripping. **Revised integration:** New diagnostics must run in both the standalone `validate` CLI command AND `write_output`'s validation pass, not just the fresh-transpile path.
5. **animation_converter** (High) — implement dual-backend selection: TweenService (dest, simple anims) vs config-table + runtime (source, blend trees/root motion). Port root motion extraction, blend tree parsing, R15 bone mapping. **Added sub-items:** (a) Update `_inject_runtime_modules()` to auto-inject `animator_bridge.luau` and `TransformAnimator.luau` when config-table or transform-only backend is selected (currently only `animator_runtime.luau` is injected). (b) Generated animation scripts must persist to disk in a known subdirectory that `write_output` rehydration handles.
6. **ui_translator** (Medium) — port font mapping, TextAnchor→alignment, sprite-vs-solid distinction, partial anchor warnings.
7. **scene_parser** (Low) — port animator controller GUID extraction and verify edge case parity.

### Phase 5: Port Tests

1. Port tests for all new modules
2. Merge test cases for reconciled shared modules
3. Ensure all tests pass in the dest repo structure
4. **Three-flow regression tests** (learned from Phase 1-2 bugfixes):
   - `assemble` preserves hand-edited scripts when `--retranspile` is absent
   - `assemble --retranspile` overwrites hand-edited scripts with fresh output
   - `upload` rebuild includes scripts in the generated place (the exact regression fixed in 86392e6)
5. **Workflow contract tests:**
   - `transpile` → `validate` workflow (transpile currently doesn't write to disk; validate reads from disk — verify this contract)
   - Duplicate scene names disambiguated in `discover`, `status`, AND `report`
   - Cross-project contamination rejected by `_make_pipeline()`
6. **Rehydration round-trip tests:**
   - Nested script directory rehydration + correct Script/LocalScript/ModuleScript retention
   - Script metadata manifest (Phase 3 item 12) correctly restores type and parent_path
7. **Interactive resume tests:**
   - `Pipeline.resume()` vs `_run_through()` divergence: resume replays upload/resolve as prerequisites, _run_through skips cloud phases — verify both paths produce consistent output
8. **Visual regression tests** (added per CEO review):
   - Convert the FPS reference project (`unity-fps-output/`), open in Roblox Studio, verify: materials render correctly (colors, textures, transparency), UI elements positioned correctly (not flipped), scripts execute without errors, animations play on correct backends
   - Compare against baseline screenshots where feasible

### Phase 6: Polish

1. Port documentation from `docs/`
2. Final README, CLAUDE.md, ARCHITECTURE.md updates
3. Verify both modes work end-to-end
4. Clean up any dead code
5. **Formally close or roadmap deferred fix C2:** upload publishes a fresh rebuild, not the reviewed .rbxlx. Either document as "by design" or add .rbxlx reader if feasible
6. **Verify dead-path cleanup:** report_generator.py and rbxl_binary_writer.py were ported in Phase 2 with no call sites — Phase 3 should have wired them, but Phase 6 must verify no ported modules remain unreferenced

---

## Detailed Integration Notes

### Type Compatibility (Source → Dest)

Ported code must use the dest's centralized type system. Key mappings:

| Source Type (ad-hoc per module) | Dest Type (`core/roblox_types.py`) |
|---|---|
| `rbxl_writer.RbxPartEntry` | `RbxPart` |
| `rbxl_writer.RbxScriptEntry` | `RbxScript` |
| `rbxl_writer.RbxSurfaceAppearance` | `RbxSurfaceAppearance` |
| `rbxl_writer.RbxWriteResult` | (no direct equivalent — add if needed) |
| `scene_parser.ParsedScene` | `core.unity_types.ParsedScene` |
| `scene_parser.SceneNode` | `core.unity_types.SceneNode` |
| `guid_resolver.GuidIndex` | `core.unity_types.GuidIndex` |
| `asset_extractor.AssetManifest` | `core.unity_types.AssetManifest` |
| `material_mapper.RobloxMaterialDef` | `MaterialMapping` (in dest's material_mapper) |

Field names also differ (e.g., source `part.light_children.append((tuple))` vs dest `part.lights.append(RbxLight(...))`). Every reference must be updated when porting.

### Import Path Mapping

| Source Import | Dest Import |
|---|---|
| `from modules import scene_parser` | `from unity.scene_parser import parse_scene` |
| `from modules import material_mapper` | `from converter.material_mapper import map_materials` |
| `from modules import code_transpiler` | `from converter.code_transpiler import transpile_scripts` |
| `from modules import rbxl_writer` | `from roblox.rbxlx_writer import write_rbxlx` |
| `from modules import roblox_uploader` | `from roblox.cloud_api import upload_asset, upload_place` |
| `from modules.conversion_helpers import X` | Various — see decomposition table |
| `import config` | `import config` (same) |

### Pipeline Integration Points

The dest's `Pipeline` class in `converter/pipeline.py` has ordered phases:
```
parse → extract_assets → upload_assets → resolve_assets → convert_materials →
transpile_scripts → convert_animations → convert_scene → write_output
```

New modules wire in as follows (updated based on Phase 1-2 learnings):

| New Module | Where in Pipeline | Integration Detail |
|---|---|---|
| `sprite_extractor` | Inside `extract_assets` | After asset manifest built, scan for spritesheet .meta files |
| `mesh_splitter` | Inside `convert_scene` | When MeshRenderer has `len(m_Materials) > 1`, split before creating RbxParts |
| `vertex_color_baker` | After `convert_materials`, before `convert_scene` | ~~Originally "between convert_materials and upload_assets"~~ — actual phase order has upload_assets before convert_materials. Corrected placement. |
| `scriptable_object_converter` | Inside `transpile_scripts` + persist to disk | Generate ModuleScripts AND write `.luau` files to `scripts/` so rehydration path picks them up when transpilation is skipped |
| `bridge_injector` | Inside `write_output` (after script materialization) | After scripts populated from either fresh transpile OR disk rehydration. Dedupe against existing RbxScript names. |
| `code_validator` | Inside `write_output` | After `luau_validator.validate_and_fix()`, run structural validation |
| `rbxl_binary_writer` | Optional post-`write_output` step | NOT wired into interactive `upload` (which uses execute_luau). For future direct Open Cloud place-upload. |
| `report_generator` | Replaces inline reporting in `write_output` + `report()` | Single reporting path — replaces ad hoc JSON in pipeline.py and convert_interactive.py |

### State Format Decision

Source uses `.convert_state.json` (flat dict). Dest uses `ConversionContext` (dataclass → JSON).

**Decision:** The interactive CLI (`convert_interactive.py`) should use `ConversionContext` as the backing store, saving to `conversion_context.json`. This unifies state between both modes. The interactive CLI adds a thin wrapper that:
- Loads `ConversionContext` at phase start
- Calls Pipeline methods for heavy lifting
- Saves `ConversionContext` at phase end
- Emits structured JSON to stdout for the skill

### Material Mapper Reconciliation (Largest Risk)

Source is 1734 LOC with richer shader support. Dest is 726 LOC with cleaner types.

**Strategy:** Keep dest's function signature and return types. Incrementally port source's capabilities:

1. Port shader identification patterns (source has 60+ shader patterns vs dest's `_SUPPORTED_SHADERS` frozenset)
2. Port additional texture operations: `bake_ao`, `threshold_alpha`, `pre_tile`, `to_grayscale`, `composite_detail`, `blend_normal_detail`, `heightmap_to_normal` (dest has `copy`, `extract_r`, `invert_a`)
3. Port `UNCONVERTED.md` generation
4. Port vertex color detection (feeds into vertex_color_baker)
5. Validate that returned `MaterialMapping` works with `scene_converter.py` and `rbxlx_writer.py`

### Physics.lua vs physics_bridge.luau — NOT Actually Conflicting

On closer inspection, these solve **different problems**:
- Source `Physics.lua`: Wraps workspace raycast/overlap queries (Unity `Physics.Raycast`, `Physics.OverlapSphere`)
- Dest `physics_bridge.luau`: Emulates `CharacterController.Move/SimpleMove/isGrounded`

**Decision:** Port `Physics.lua` as `physics_queries.luau` alongside `physics_bridge.luau`. No conflict.

### AnimatorBridge.lua vs animator_runtime.luau — Keep Both

- Source `AnimatorBridge.lua`: Config-table-driven state machine with blend tree + parameter-driven transitions. Consumes data generated by source's animation_converter.
- Dest `animator_runtime.luau`: JSON-based controller interpretation using `Animator:LoadAnimation()`.

**Decision:** Keep `animator_runtime.luau` as primary (more mature). Port `AnimatorBridge.lua` as `animator_bridge.luau` alongside it. Auto-detect which to use based on config format.

### Config Merge

Add to dest's `config.py`:
```python
EMIT_PACKAGES: bool = True
PACKAGES_SUBDIR: str = "packages"
REPORT_VERBOSE: bool = True
UNCONVERTED_FILENAME: str = "UNCONVERTED.md"
```

Change in dest's `config.py`:
```python
# ".asset": "unknown"  →  ".asset": "scriptable_object"
```

Keep dest's `ANTHROPIC_MODEL = "claude-sonnet-4-6"` (newer than source's `"claude-opus-4-5"`).

### Dependency Additions (`pyproject.toml`)

```toml
lz4 >= 4.0    # for rbxl_binary_writer
```

Optional (documented but not required):
- `pyassimp` — for FBX vertex color baking
- `libassimp` system library

---

## Dependency Graph

```
Phase 1 ✅ (docs + entry points)
Phase 2 ✅ (standalone modules + bridge Luau files)

Phase 3 (pipeline integration — depends on Phase 2):
  3.1  bridge_injector → write_output (after script materialization)
  3.2  vertex_color_baker → after convert_materials, before convert_scene
  3.3  sprite_extractor → inside extract_assets
  3.4  mesh_splitter → inside convert_scene
  3.5  scriptable_object_converter → transpile_scripts + persist to disk
  3.6  rbxl_binary_writer → optional post-write_output (NOT in upload path)
  3.7  report_generator → replace inline reporting
  3.8  generate_bootstrap_script → inside write_output
  3.9  extract_serialized_field_refs → before write_output, persist results
  3.10 generate_prefab_packages → inside write_output or persist metadata
  3.11 extend write_output disk rewrite for new subdirectories
  3.12 add script metadata persistence (script_manifest.json)

Phase 4 (reconciliation — can overlap with Phase 3):
  4.1 api_mappings (independent)
  4.2 material_mapper (largest effort, independent; needs idempotence under replay)
  4.3 code_transpiler (depends on 4.1; must persist dependency info)
  4.4 luau_validator patterns (independent; dual integration: validate cmd + write_output)
  4.5 animation_converter (independent; needs runtime injection update + script persistence)
  4.6 ui_translator (independent)
  4.7 scene_parser (independent)

Phase 5 (tests — do alongside each phase, expanded):
  + three-flow regression tests (CLI, interactive-fresh, interactive-rehydrated)
  + workflow contract tests (transpile→validate, cross-project guard)
  + rehydration round-trip tests
  + resume path divergence tests (Pipeline.resume vs _run_through)

Phase 6 (polish — last):
  + close/roadmap deferred C2 (upload rebuild vs reviewed .rbxlx)
  + verify no ported modules remain unreferenced
```

---

## Risk Areas

| Risk | Mitigation |
|---|---|
| `Physics.lua` vs `physics_bridge.luau` — different API surfaces | ✅ Resolved: ported as `physics_queries.luau` alongside `physics_bridge.luau` |
| `AnimatorBridge.lua` vs `animator_runtime.luau` — different animation approaches | ✅ Resolved: ported as `animator_bridge.luau` alongside `animator_runtime.luau`. Phase 4.5 adds backend selection. |
| Binary writer integration — dest uses Luau Execution API for headless publishing | Binary writer is optional post-write_output step for future direct place-upload. NOT wired into interactive upload. |
| `conversion_helpers.py` decomposition — 2087 LOC of orchestration logic | Most already exists in dest's scene_converter + component_converter. Only port the 3-4 functions that don't exist |
| Test count growth (source ~1200 + dest ~950) | Run full suite incrementally; fix failures as they arise |
| Import path changes — source uses flat `modules.X`, dest uses `converter.X`, `unity.X`, `roblox.X` | Systematic find-replace during each port step |
| **NEW: Script rehydration lossy for Phase 3/4 additions** | Rehydration infers type heuristically, uses only stem, drops directory identity. Add script_manifest.json (Phase 3 item 12) before wiring new script-generating modules. |
| **NEW: bridge_injector double-injection** | bridge_injector dedupes by filename but RbxScript.name is basename-only. Must dedupe against existing RbxScript entries during write_output integration. |
| **NEW: Pipeline.resume() vs _run_through() divergence** | resume() replays upload/resolve; _run_through() skips cloud phases. New Phase 3/4 integrations that depend on upload/resolve must handle both paths. |
| **NEW: Dead-path drift** | report_generator.py and rbxl_binary_writer.py ported in Phase 2 with zero call sites. Phase 3 must wire them; Phase 6 must verify. |

---

## Success Criteria

- [x] Both `python u2r.py convert ...` and `/convert-unity ...` produce correct .rbxlx output (Phase 1)
- [x] Runtime Luau files from both repos coexist in `runtime/` (Phase 2)
- [x] Interactive mode supports resume via `conversion_context.json` (Phase 1, fixed in Phase 2)
- [ ] All existing dest tests pass (1020+)
- [ ] All ported source tests pass
- [ ] New modules (bridge_injector, vertex_color_baker, sprite_extractor, mesh_splitter, scriptable_object_converter, rbxl_binary_writer) are integrated into pipeline and tested (Phase 3)
- [ ] No ported module remains unreferenced (report_generator and rbxl_binary_writer currently have zero call sites)
- [ ] Three-flow regression tests pass: CLI, interactive-fresh, interactive-rehydrated (Phase 5)
- [ ] Script rehydration is lossless via script_manifest.json (Phase 3 item 12)
- [ ] README clearly documents both modes with examples (Phase 6)
- [ ] CLAUDE.md accurately describes the merged architecture (Phase 6)
