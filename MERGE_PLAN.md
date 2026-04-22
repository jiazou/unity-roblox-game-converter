# Merge Plan: unity-roblox-game-converter → unity2rbxlx

## Goal

Merge the `unity-roblox-game-converter` repo (hereafter **"source"**) into the `unity2rbxlx` repo (hereafter **"dest"**). The dest repo is the surviving codebase. The final result has two modes:

1. **Claude Code Skill** (`/convert-unity`) — interactive, phase-by-phase conversion with human decision points at each stage. Powered by `convert_interactive.py` and the `.claude/skills/convert-unity/` skill definition.
2. **CLI Tool** (`u2r.py`) — fully automated, runs all pipeline phases end-to-end. Existing in the dest repo today.

---

## Dest drift since plan was written

Between the plan's last structural review (2026-04-12) and Phase 4 kickoff (2026-04-22), the dest repo `ntornow/unity2rbxlx` made architectural changes that were not captured in prior revisions of this plan. Phase 4 work must account for these up front.

- **Inline-over-runtime-wrappers policy adopted** (`converter/docs/design/inline-over-runtime-wrappers.md`). Unity APIs are translated at transpile time via `API_CALL_MAP` / `LIFECYCLE_MAP` / `UTILITY_FUNCTIONS`, not via runtime wrapper modules. Runtime modules are only permitted when the Unity feature is "genuinely stateful across frames and events."
- **Nine runtime bridges + two Python modules deleted.** Deleted: `Time.luau`, `Coroutine.luau`, `physics_queries.luau`, `GameObjectUtil.luau`, `Input.luau`, `MonoBehaviour.luau`, `StateMachine.luau`, `TransformAnimator.luau`, `animator_bridge.luau`, plus `bridge_injector.py` and `mesh_splitter.py`.
- **Consolidations (not simple deletions):** `animator_bridge.luau` unique capabilities merged into `animator_runtime.luau`. `TransformAnimator.luau`'s curve-based CFrame/Size animation reimplemented as inline TweenService output inside `animation_converter.py` (confirmed by the policy doc's "History" section).
- **Approved surviving runtimes:** `animator_runtime.luau`, `nav_mesh_runtime.luau`, `event_system.luau`, `physics_bridge.luau`, `cinemachine_runtime.luau`. Plus feature-specific runtimes: `object_pool.luau`, `pickup_runtime.luau`, `sub_emitter_runtime.luau`.
- **`luau_validator.py` removed** (commit `0d2051fd`). Today the dest has no Luau syntax/structural validation — `pipeline.py` never validates transpiled Luau; `u2r.py validate` is XML-only. Phase 4.4 ports source's `code_validator.py` to fill this gap (the policy doc itself names `luau_validator.py` as an approved inline fix-up mechanism, so restoring it is policy-aligned).
- **New pipeline phase:** `moderate_assets` now sits between `extract_assets` and `upload_assets` (`pipeline.py:27–36`). Order: `parse → extract_assets → moderate_assets → upload_assets → resolve_assets → convert_materials → transpile_scripts → convert_animations → convert_scene → write_output`.
- **New modules in dest that the plan never named:** `converter/converter/asset_moderator.py`, `converter/converter/storage_classifier.py`, `converter/converter/fbx_binary.py`, `converter/roblox/health_check_injector.py`, `converter/roblox/luau_injector.py`, `converter/roblox/studio_log_parser.py`, `converter/utils/image_processing.py`, `converter/utils/logging_config.py`. Smoke-test infrastructure (`smoke_test.py`, Studio launcher + log parser) also added. Treat these as out-of-scope for the merge but aware of their presence when wiring Phase 4 items.
- **Rehydration key renamed.** Plan referred to `script_manifest.json`; dest landed it as `conversion_plan.json` containing `storage_plan` + `script_paths`.
- **Bootstrap superseded.** The "port `generate_bootstrap_script()`" item from conversion_helpers decomposition was replaced by `GameServerManager` auto-injection; do not port.

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
| ~~`modules/bridge_injector.py`~~ | **SUPERSEDED** | Deleted on dest per inline-over-runtime policy (see Dest drift). Auto-injection no longer needed. |
| `modules/vertex_color_baker.py` | `converter/converter/vertex_color_baker.py` | Bake mesh vertex colors to textures (Roblox ignores FBX vertex colors) |
| `modules/sprite_extractor.py` | `converter/converter/sprite_extractor.py` | Extract sprites from spritesheets via .meta TextureImporter data |
| ~~`modules/mesh_splitter.py`~~ | **SUPERSEDED** | Deleted on dest; replaced by `scene_converter`'s sub-mesh hierarchy (see Dest drift). |
| `modules/scriptable_object_converter.py` | `converter/converter/scriptable_object_converter.py` | Convert .asset ScriptableObjects → Luau data tables |
| `modules/rbxl_binary_writer.py` | `converter/roblox/rbxl_binary_writer.py` | XML .rbxlx → binary .rbxl (required for Open Cloud Place API) |
| `modules/report_generator.py` | `converter/converter/report_generator.py` | Generate JSON conversion report |
| `modules/code_validator.py` | Merge into `converter/converter/luau_validator.py` | Luau syntax validation (complement dest's richer validator) |
| `modules/unity_yaml_utils.py` | Merge into `converter/unity/yaml_parser.py` | YAML parsing utilities (compare for unique helpers) |
| `convert_interactive.py` | `converter/convert_interactive.py` | Interactive phase-based CLI for skill |
| `modules/conversion_helpers.py` | Split across dest modules | Large orchestration module — see decomposition plan below |

#### Bridge/Runtime Luau Files

> **SUPERSEDED by dest drift.** The original plan called for porting all 9 source bridge files. The dest subsequently adopted `inline-over-runtime-wrappers.md` and deleted 9 runtime bridges. The final approved runtime set on dest `main` is documented in the Dest drift section at the top of this file. Table below kept for historical reference.

| Source (`bridge/`) | Final Status on dest `main` |
|---|---|
| `Input.lua` | ❌ **Deleted** — inlined via `UserInputService` calls |
| `Time.lua` | ❌ **Deleted** — inlined via `RunService` + `tick()` |
| `MonoBehaviour.lua` | ❌ **Deleted** — lifecycle inlined |
| `Coroutine.lua` | ❌ **Deleted** — inlined via `task.spawn` / `task.wait` |
| `GameObjectUtil.lua` | ❌ **Deleted** — inlined via `Instance` APIs |
| `StateMachine.lua` | ❌ **Deleted** — inlined |
| `TransformAnimator.lua` | ❌ **Deleted** — curve-based CFrame/Size inlined as TweenService output in `animation_converter.py` |
| `AnimatorBridge.lua` | ❌ **Deleted** — unique capabilities merged into `animator_runtime.luau` |
| `Physics.lua` | ❌ **Deleted** (was `physics_queries.luau`) — inlined via `workspace:Raycast` / `workspace:GetPartsBoundInBox` |
| `animator_runtime.luau` | ✅ **Approved runtime** (state machine) — now carries absorbed `AnimatorBridge` features |
| `cinemachine_runtime.luau` | ✅ **Approved runtime** (virtual camera state) |
| `event_system.luau` | ✅ **Approved runtime** (UnityEvent wiring) |
| `nav_mesh_runtime.luau` | ✅ **Approved runtime** (pathfinding) |
| `physics_bridge.luau` | ✅ **Approved runtime** (CharacterController physics constraints) |
| `object_pool.luau` | ✅ Approved feature runtime |
| `pickup_runtime.luau` | ✅ Approved feature runtime |
| `sub_emitter_runtime.luau` | ✅ Approved feature runtime |

#### Skill Definition & Interactive Mode

| Source | Dest | Purpose |
|---|---|---|
| `.claude/skills/convert-unity/SKILL.md` | `converter/.claude/skills/convert-unity/SKILL.md` | Claude Code skill definition |
| `.claude/skills/convert-unity/references/upload-patching.md` | Same, ported | Game logic porting guidance |
| `.claude/skills/review-csharp-lua-conversion/` | Archived — skip | Already marked archived in source |

#### Tests

| Source Test File | Dest Location | Notes |
|---|---|---|
| ~~`tests/test_bridge_injector.py`~~ | **SUPERSEDED** | Not needed; module deleted |
| `tests/test_vertex_color_baker.py` | `converter/tests/test_vertex_color_baker.py` | New |
| `tests/test_sprite_extractor.py` | `converter/tests/test_sprite_extractor.py` | New |
| ~~`tests/test_mesh_splitter.py`~~ | **SUPERSEDED** | Not needed; module deleted |
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
| Luau validator | `modules/code_validator.py` | **Removed on dest `main`** (was `converter/converter/luau_validator.py`; deleted in commit `0d2051fd`) | **Retargeted in Phase 4.4:** port source's `code_validator.py` as the new Luau validator; the `inline-over-runtime-wrappers.md` policy explicitly names this module as an approved fix-up mechanism. |

### Decomposing `conversion_helpers.py`

The source's `conversion_helpers.py` (2087 LOC) is a large module that handles orchestration logic. In the dest repo, this is already decomposed:

| Source Function | Dest Equivalent |
|---|---|
| `scene_nodes_to_parts()` | `converter/scene_converter.py` |
| `node_to_part()` | `converter/scene_converter.py` + `converter/component_converter.py` |
| `apply_collider_properties()` | `converter/component_converter.py:convert_collider()` |
| `convert_light_components()` | `converter/component_converter.py:convert_light()` |
| `convert_audio_components()` | `converter/component_converter.py:convert_audio()` |
| `generate_bootstrap_script()` | **SUPERSEDED** — replaced by `GameServerManager` auto-injection in `pipeline.py:2015–2020`; do not port |
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

### Phase 2: Port New Standalone Modules ✅ (with post-merge deletions)

**Status:** Originally merged (branch `merge-converters-phase2`). **Significant post-merge deletions** occurred on dest `main` before Phase 3 per the `inline-over-runtime-wrappers.md` policy — see [Dest drift since plan was written](#dest-drift-since-plan-was-written) below for the full story.

Delivered initially: all 7 standalone Python modules and 9 bridge Luau files, plus `config.py` updates.

**Subsequently deleted on dest `main`** (per `converter/docs/design/inline-over-runtime-wrappers.md`):
- `bridge_injector.py` — injector mechanism removed alongside its targets.
- `mesh_splitter.py` — superseded by `scene_converter`'s sub-mesh hierarchy.
- Nine runtime bridges: `Time.luau`, `Coroutine.luau`, `physics_queries.luau`, `GameObjectUtil.luau`, `Input.luau`, `MonoBehaviour.luau`, `StateMachine.luau`, `TransformAnimator.luau`, `animator_bridge.luau`.
- `animator_bridge.luau`'s unique capabilities (blend trees, Any-state transitions, `Play()`, `Destroy()`, lazy track loading, getters) consolidated into `animator_runtime.luau`.
- `TransformAnimator.luau`'s curve-based CFrame/Size animation consolidated into `animation_converter.py`'s inline TweenService output.

**Surviving Phase 2 artifacts on dest `main`:** `vertex_color_baker.py` (unwired — see Phase 4.8), `sprite_extractor.py` (wired Phase 3), `scriptable_object_converter.py` (wired Phase 3), `rbxl_binary_writer.py` (wired Phase 3), `report_generator.py` (wired Phase 3). Approved runtimes in `converter/runtime/`: `animator_runtime.luau`, `nav_mesh_runtime.luau`, `event_system.luau`, `physics_bridge.luau`, `cinemachine_runtime.luau` (plus game-feature runtimes `object_pool.luau`, `pickup_runtime.luau`, `sub_emitter_runtime.luau`).

**Post-merge fixes applied (86392e6):**
- assemble `--retranspile` flag: skip transpilation when already completed to preserve hand-edited Luau
- pipeline.write_output: rehydrate scripts from disk when transpilation was skipped
- upload: added `write_output` to rebuild phase list (was missing scripts)
- Scene paths: project-relative paths instead of basename-only for disambiguation
- Cross-project contamination guard: hard-fail when persisted context comes from a different Unity project

### Phase 3: Integrate New Modules into Pipeline ✅ (with supersessions)

**Status:** Closed per `converter/docs/design/merge-plan-phase-3-augmented.md`. Outcome vs. the original 12-item list:

- **Landed (5):** sprite extractor wiring (3), scriptable object converter + disk persistence (5), binary writer wiring with content-type detection (6), report generator adoption (7), rehydration via `conversion_plan.json` (12 — renamed from `script_manifest.json` and stored as `{storage_plan, script_paths}` in `pipeline.py:1676`, read at `:1629`).
- **Superseded (3):** bridge injection (1) — replaced by inline-over-runtime-wrappers policy; mesh splitting (4) — replaced by `scene_converter`'s sub-mesh hierarchy; bootstrap script generation (8) — replaced by `GameServerManager` auto-injection (`pipeline.py:2015–2020`).
- **Deferred (4) — rolled into Phase 4 as 4.8–4.11:** vertex color baking (2), `extract_serialized_field_refs` (9), `generate_prefab_packages` (10), disk rewrite for `animation_data/` + `packages/` (11).
- **Also landed in the same window:** `luau_validator.py` was removed from dest (commit `0d2051fd` "reconcile upstream phase-4 refactor with luau-analyze migration — integrated storage_classifier and removed luau_validator"). Phase 4.4 now addresses the missing validation layer.

**Original goal (kept for historical context):** Wire the Phase 2 modules into the existing `Pipeline` class. All integrations must work in three flows: (a) full `u2r.py` CLI, (b) interactive `assemble` with fresh transpilation, (c) interactive `assemble` with `--retranspile=false` (script rehydration path). The `upload` command's rebuild path (`parse → … → write_output`) must also include every new step.

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

### Phase 4: Reconcile Shared Modules + Close Phase 3 Deferred Items

**Goal:** For modules in both repos, take the best of both. Close the four Phase 3 items that were deferred. **See [MERGE_PLAN_PHASE4.md](MERGE_PLAN_PHASE4.md) for the detailed plan** with per-module diffs, step-by-step actions, acceptance criteria, and execution order.

> **Key lesson from Phase 1-2:** Interactive mode can skip `transpile_scripts` entirely. Any reconciliation work that only populates `PipelineState` or `state.transpilation_result` will be invisible to the preserved-script assemble and upload rebuild paths. Reconciled modules must persist their outputs or integrate at `write_output` time.
> **Key constraint from dest drift:** All ported code must respect the inline-over-runtime-wrappers policy. Source mappings and prompt rules that reference deleted bridges (`AnimatorBridge`, `Input`, `Time`, `MonoBehaviour`, `Coroutine`, `GameObjectUtil`, `StateMachine`, `physics_queries`, `TransformAnimator`) must be rewritten to inline Luau before port.

Summary:

1. **api_mappings** (Low) — union merge of mapping tables, dedup. Dest is superset; port source-only entries. **New criterion:** ported entries must produce inline Luau (no `require()` of deleted bridges).
2. **material_mapper** (High) — port 14+ missing shaders, 6 missing texture ops, unconverted feature tracking, vertex color detection into dest's cleaner type system. **Added criterion:** Must be idempotent under interactive prerequisite replay — companion scripts, UNCONVERTED.md, and vertex-color outputs must not assume upload/resolve already ran.
3. **code_transpiler** (Medium) — port dependency-aware context building (topological sort + dependency Luau injection, with deterministic alphabetical cycle-break) and C# pattern analysis warnings into dest's concurrent dual-strategy transpiler. **Added criteria:** (a) transpiled Luau contains zero `require()` calls targeting deleted bridges; (b) dependency ordering and warnings must be persisted (via `conversion_plan.json` or `conversion_context.json`) so the preserved-script path doesn't lose them.
4. **luau_validator** (Low) — **retargeted.** Dest's `luau_validator.py` was removed; port source's `code_validator.py` as the replacement. Wire into `write_output` and `u2r.py validate`. Include `check_method_completeness()` as a diagnostic. Aligned with the `inline-over-runtime-wrappers.md` policy which names `luau_validator.py` as an approved fix-up mechanism.
5. **animation_converter** (High) — **retargeted.** Dest already inlines curve-based CFrame/Size animation via TweenService (`TransformAnimator.luau` is deleted; see dest drift). Phase 4 work: port source's transform-only *detection and scene/prefab scanning* only, routing to dest's existing inline TweenService generator. Blend-tree-bearing humanoid clips continue to route to `animator_runtime.luau` (which absorbed `animator_bridge.luau`'s blend tree support). R15 bone map ported as the routing predicate. Root motion dropped from Phase 4 (roadmap). Scene-scoped naming is new behavior introduced during the port.
6. **ui_translator** (Medium) — port font mapping, TextAnchor→alignment, sprite-vs-solid distinction, partial anchor warnings. Audit Y-inversion at `translate_rect_transform` against `unity-fps-output` before merging.
7. **scene_parser** (Low) — port animator controller GUID extraction and verify edge case parity.
8. **vertex_color_baker wiring** (Medium) — deferred Phase 3 item 2. Wire existing unwired module (`converter/converter/vertex_color_baker.py`, 18 KB on disk) into the pipeline; depends on 4.2's `uses_vertex_colors` flag.
9. **extract_serialized_field_refs** (Medium) — deferred Phase 3 item 9. Port from source's `conversion_helpers.py`; results persisted to `conversion_context.json`.
10. **generate_prefab_packages** (High) — deferred Phase 3 item 10. Port with architecture review; depends on the disk rewrite below (4.11).
11. **Disk rewrite for `animation_data/` + `packages/`** — deferred Phase 3 item 11. Extend `write_output`'s disk-rewrite to handle the new subdirectories so rehydration stays lossless.

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

The dest's `Pipeline` class in `converter/converter/pipeline.py` has ordered phases (confirmed at `pipeline.py:27–36`):
```
parse → extract_assets → moderate_assets → upload_assets → resolve_assets →
convert_materials → transpile_scripts → convert_animations → convert_scene → write_output
```

Integration status after Phase 3 + dest drift:

| Module | Where in Pipeline | Status |
|---|---|---|
| `sprite_extractor` | Inside `extract_assets` | ✅ Landed Phase 3 |
| `scriptable_object_converter` | `transpile_scripts` → disk write in `write_output` | ✅ Landed Phase 3 (moved to `write_output` to avoid rmtree deletion, per commit `f726a6af`) |
| `rbxl_binary_writer` | Post-`write_output` optional step | ✅ Landed Phase 3 (`skip_binary_rbxl` flag threaded through) |
| `report_generator` | Replaces inline reporting in `write_output` | ✅ Landed Phase 3 |
| `conversion_plan.json` rehydration | Read at `pipeline.py:1629`, written at `:1676` with `storage_plan` + `script_paths` | ✅ Landed Phase 3 (renamed from `script_manifest.json`) |
| `GameServerManager` auto-injection | Inside `write_output` (`pipeline.py:2015–2020`) | ✅ Landed Phase 3 — supersedes `generate_bootstrap_script()` |
| `mesh_splitter` | — | ❌ Deleted; superseded by `scene_converter` sub-mesh hierarchy |
| `bridge_injector` | — | ❌ Deleted with the nine runtime bridges per inline-over-runtime policy |
| `vertex_color_baker` | After `convert_materials`, before `convert_scene` | ⏳ **Deferred to Phase 4.8** — module exists unwired; needs `uses_vertex_colors` flag from 4.2 |
| `code_validator` (ported) | Inside `write_output` + `u2r.py validate` subcommand | ⏳ **Phase 4.4** — dest has no Luau validator today; port source's `code_validator.py` |
| `extract_serialized_field_refs` | Before `write_output`; persist to `conversion_context.json` | ⏳ **Deferred to Phase 4.9** |
| `generate_prefab_packages` | Inside `write_output`; writes `packages/` | ⏳ **Deferred to Phase 4.10** |
| Disk rewrite for `animation_data/`+`packages/` | Inside `write_output` rehydration | ⏳ **Deferred to Phase 4.11** |

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

### Physics.lua vs physics_bridge.luau — SUPERSEDED

> Historical note: the plan originally called for porting `Physics.lua` as `physics_queries.luau` alongside dest's `physics_bridge.luau`. Per the inline-over-runtime policy, `physics_queries.luau` was deleted; Unity raycast/overlap queries are now inlined via `workspace:Raycast` and `workspace:GetPartsBoundInBox`. `physics_bridge.luau` remains as the approved runtime for `CharacterController` emulation (stateful).

### AnimatorBridge.lua vs animator_runtime.luau — SUPERSEDED

> Historical note: the plan originally called for porting `AnimatorBridge.lua` as `animator_bridge.luau` alongside dest's `animator_runtime.luau`. Per the inline-over-runtime policy, `animator_bridge.luau` was deleted; its unique capabilities (blend trees, Any-state, `Play()`, `Destroy()`, lazy tracks, getters) were merged into `animator_runtime.luau`. Phase 4.5 now routes humanoid clips to the single runtime and transform-only clips to inline TweenService. No dual runtime.

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
Phase 2 ✅ (with post-merge deletions per inline-over-runtime policy)
Phase 3 ✅ (5 landed, 3 superseded, 4 deferred to Phase 4)

Phase 4 (reconciliation + deferred-Phase-3 closeout):
  Reconciliation (order by dependency):
    4.7 scene_parser (independent; controller GUIDs feed 4.5)
    4.1 api_mappings (independent; no require() of deleted bridges)
    4.6 ui_translator (independent; Y-inversion audit required)
    4.5 animation_converter (depends on 4.7; route to animator_runtime or inline TweenService)
    4.2 material_mapper (depends on vertex_color_baker presence; wiring covered by 4.8)
    4.3 code_transpiler (strip deleted-bridge require() from prompt + mappings; deterministic topo sort)
    4.4 luau_validator (port code_validator.py; wire into write_output + u2r.py validate)
  Phase 3 deferred closeout:
    4.8 vertex_color_baker wiring (depends on 4.2's uses_vertex_colors flag)
    4.9 extract_serialized_field_refs (persist to conversion_context.json)
    4.10 generate_prefab_packages (depends on 4.11 disk rewrite)
    4.11 disk rewrite for animation_data/+packages/ subdirectories

Phase 5 (tests — do alongside each Phase 4 item):
  + three-flow regression tests (CLI, interactive-fresh, interactive-rehydrated)
  + cross-module integration tests (scene_parser→animation, material→rbxlx_writer, transpiler→validator)
  + rehydration round-trip tests via conversion_plan.json
  + resume path divergence tests (Pipeline.resume vs _run_through)
  + test_no_rejected_bridges.py expansion (lint for require() of deleted bridges)
  + visual regression pass on unity-fps-output/ after Phase 4

Phase 6 (polish — last):
  + close/roadmap deferred C2 (upload rebuild vs reviewed .rbxlx)
  + roadmap root motion (dropped from Phase 4, needs real-FBX spike)
  + verify no ported modules remain unreferenced
```

---

## Risk Areas

| Risk | Mitigation |
|---|---|
| `Physics.lua` vs `physics_bridge.luau` | ✅ Obsolete: `physics_queries.luau` deleted per inline-over-runtime policy; dest keeps `physics_bridge.luau` for stateful physics behaviors only |
| `AnimatorBridge.lua` vs `animator_runtime.luau` | ✅ Resolved: `animator_bridge.luau` deleted; unique capabilities merged into `animator_runtime.luau`. Phase 4.5 routes clips to the single runtime or to inline TweenService — no dual backend. |
| Binary writer integration — dest uses Luau Execution API for headless publishing | ✅ Resolved Phase 3: binary writer wired as optional post-`write_output` step with `skip_binary_rbxl` flag. NOT wired into interactive upload path. |
| `conversion_helpers.py` decomposition — 2087 LOC of orchestration logic | Most already exists in dest's scene_converter + component_converter. `generate_bootstrap_script()` superseded. Remaining ports are `extract_serialized_field_refs` (4.9) and `generate_prefab_packages` (4.10). |
| Test count growth (source ~1200 + dest ~950) | Run full suite incrementally; fix failures as they arise |
| Import path changes — source uses flat `modules.X`, dest uses `converter.X`, `unity.X`, `roblox.X` | Systematic find-replace during each port step |
| Script rehydration lossy for Phase 3/4 additions | ✅ Resolved Phase 3 via `conversion_plan.json` (renamed from `script_manifest.json`). Phase 4.11 extends the disk rewrite to cover `animation_data/` and `packages/`. |
| Pipeline.resume() vs _run_through() divergence | resume() replays upload/resolve; _run_through() skips cloud phases. New Phase 4 integrations that depend on upload/resolve must handle both paths. |
| Dead-path drift | `report_generator.py` and `rbxl_binary_writer.py` wired in Phase 3. `vertex_color_baker.py` remains unwired (Phase 4.8 closes this). Phase 6 verifies no module remains unreferenced. |
| **NEW: Inline-over-runtime policy violations during port** | Source prompt rules and api_mappings entries reference deleted bridges. Phase 4.1 and 4.3 must strip/rewrite these before port; automated test enforces zero `require()` of deleted bridges in transpiled output. |
| **NEW: Luau validator gap** | No Luau syntax/structural validation exists on dest today. Phase 4.4 restores it by porting source's `code_validator.py`, policy-aligned with `inline-over-runtime-wrappers.md`. |
| **NEW: Dest drift during Phase 4 execution** | The dest made architectural changes between Phase 2 and Phase 4 kickoff that invalidated parts of this plan. Mitigate by re-auditing dest `main` at the start of each Phase 4 PR and updating the plan in-place if drift occurs again. |
| **NEW: Plan staleness (TODO.md in dest)** | Dest's `converter/TODO.md` references `luau_validator.py:5334` as still present even though the file was deleted. The policy doc `inline-over-runtime-wrappers.md` also names `luau_validator.py` as approved even though it's removed. Do not rely on dest doc accuracy — verify against tree + imports. |

---

## Success Criteria

- [x] Both `python u2r.py convert ...` and `/convert-unity ...` produce correct .rbxlx output (Phase 1)
- [x] ~~Runtime Luau files from both repos coexist in `runtime/`~~ — superseded by inline-over-runtime-wrappers policy (nine runtime bridges deleted; only stateful runtimes kept)
- [x] Interactive mode supports resume via `conversion_context.json` (Phase 1, fixed in Phase 2)
- [x] Script rehydration is lossless via `conversion_plan.json` (Phase 3 item 12, renamed from `script_manifest.json`)
- [x] Integrated Phase 2 modules into pipeline (Phase 3): sprite_extractor, scriptable_object_converter, rbxl_binary_writer, report_generator. `bridge_injector` and `mesh_splitter` superseded and deleted.
- [ ] All existing dest tests pass (dest test count grew with Phase 3 additions including `test_phase3_final_gaps.py`, `test_rehydration_plan.py`, `test_no_rejected_bridges.py`)
- [ ] All ported source tests pass
- [ ] Phase 4 deferred-Phase-3 items closed: vertex_color_baker wired (4.8), extract_serialized_field_refs (4.9), generate_prefab_packages (4.10), disk rewrite for `animation_data/`+`packages/` (4.11)
- [ ] Luau validator restored via port of `code_validator.py` (Phase 4.4)
- [ ] Zero `require()` of deleted bridges (`AnimatorBridge`, `Input`, `Time`, `MonoBehaviour`, `Coroutine`, `GameObjectUtil`, `StateMachine`, `physics_queries`, `TransformAnimator`) in transpiled output (Phase 4.1 + 4.3)
- [ ] Three-flow regression tests pass: CLI, interactive-fresh, interactive-rehydrated (Phase 5)
- [ ] Visual regression pass on `unity-fps-output/` in Roblox Studio after Phase 4 (Phase 5 success criterion)
- [ ] README clearly documents both modes with examples (Phase 6)
- [ ] CLAUDE.md accurately describes the merged architecture, including the inline-over-runtime-wrappers policy (Phase 6)
