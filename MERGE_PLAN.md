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

### Phase 1: Two-Mode Entry Points & Documentation

**Goal:** Establish the two-mode architecture and documentation before porting any modules.

1. **Create `convert_interactive.py`** in `converter/`
   - Click-based CLI with subcommands: preflight, status, discover, inventory, materials, transpile, validate, assemble, upload, report
   - Uses the same `ConversionContext` for state persistence
   - Each subcommand reads/writes `.convert_state.json`
   - Outputs structured JSON to stdout
   - Initially delegates to the existing `Pipeline` class for heavy lifting

2. **Create `.claude/skills/convert-unity/`** in `converter/`
   - `SKILL.md` — skill definition with workflow, decision points
   - `references/upload-patching.md` — detailed game logic porting guidance

3. **Update `README.md`** to clearly document both modes:
   - Quick start for CLI: `python u2r.py convert ...`
   - Quick start for Claude Code: `/convert-unity <project> <output>`
   - Feature comparison table (CLI vs skill)

4. **Update `CLAUDE.md`** to reflect:
   - Both entry points and when to use each
   - Updated architecture with new modules
   - Phase descriptions for both modes

5. **Update `ARCHITECTURE.md`** with:
   - Two-mode diagram
   - Module inventory (existing + planned)

### Phase 2: Port New Standalone Modules

**Goal:** Add source-only modules that have no dest equivalent. These are standalone (no cross-module imports) so they can be ported independently.

Order (least to most dependencies):

1. **`bridge_injector.py`** → `converter/converter/bridge_injector.py`
   - Adapt: change bridge file path from `bridge/` to `runtime/`
   - Add bridge Luau files to `runtime/` (rename `.lua` → `.luau`)

2. **`vertex_color_baker.py`** → `converter/converter/vertex_color_baker.py`
   - Standalone — no type changes needed
   - Add `assimp` to optional dependencies in pyproject.toml

3. **`sprite_extractor.py`** → `converter/converter/sprite_extractor.py`
   - Standalone — uses Pillow (already a dependency)

4. **`mesh_splitter.py`** → `converter/converter/mesh_splitter.py`
   - Standalone — uses trimesh (already a dependency)

5. **`scriptable_object_converter.py`** → `converter/converter/scriptable_object_converter.py`
   - Standalone — uses PyYAML (already a dependency)

6. **`rbxl_binary_writer.py`** → `converter/roblox/rbxl_binary_writer.py`
   - Standalone — uses lz4 (add to dependencies)

7. **`report_generator.py`** → `converter/converter/report_generator.py`
   - Adapt to use `ConversionContext` stats

8. **Port bridge Luau files** to `converter/runtime/`:
   - `Input.lua` → `Input.luau`
   - `Time.lua` → `Time.luau`
   - `MonoBehaviour.lua` → `MonoBehaviour.luau`
   - `Coroutine.lua` → `Coroutine.luau`
   - `GameObjectUtil.lua` → `GameObjectUtil.luau`
   - `StateMachine.lua` → `StateMachine.luau`
   - `TransformAnimator.lua` → `TransformAnimator.luau`
   - Reconcile `AnimatorBridge.lua` with `animator_runtime.luau`
   - Reconcile `Physics.lua` with `physics_bridge.luau`

For each module: port, adapt imports, run tests.

### Phase 3: Integrate New Modules into Pipeline

**Goal:** Wire the new modules into the existing `Pipeline` class.

1. **Add bridge injection** after `transpile_scripts` phase
   - Scan transpiled Luau for API patterns
   - Auto-inject matching runtime modules

2. **Add vertex color baking** to asset processing
   - After asset extraction, before upload
   - Bake meshes that use vertex colors

3. **Add sprite extraction** to asset extraction
   - Scan .meta files for spritesheet TextureImporters

4. **Add mesh splitting** to mesh processing
   - Before decimation, split multi-material meshes

5. **Add scriptable object conversion** to transpilation phase
   - Scan for .asset files, generate ModuleScript data tables

6. **Add binary writer** to upload flow
   - Convert .rbxlx → .rbxl before Open Cloud upload

7. **Add report generation** as final phase

8. **Port `generate_bootstrap_script()`** from conversion_helpers
   - Generates GameBootstrap.lua lifecycle script

9. **Port `extract_serialized_field_refs()`** from conversion_helpers
   - Finds MonoBehaviour fields referencing assets

10. **Port `generate_prefab_packages()`** from conversion_helpers
    - Creates per-prefab packages for ReplicatedStorage/Templates

### Phase 4: Reconcile Shared Modules

**Goal:** For modules in both repos, take the best of both.

1. **api_mappings** — merge mapping tables (union). Run dedup.
2. **material_mapper** — compare shader support. Port any missing shaders/texture ops from source.
3. **code_transpiler** — compare prompts and confidence scoring. Port better prompt engineering.
4. **luau_validator** — port any unique fix patterns from source's code_validator.
5. **animation_converter** — compare. Source has root motion extraction + blend trees. Port missing features.
6. **ui_translator** — compare. Port missing element types.
7. **scene_parser** — source may handle edge cases dest doesn't. Diff and port.

### Phase 5: Port Tests

1. Port tests for all new modules
2. Merge test cases for reconciled shared modules
3. Ensure all tests pass in the dest repo structure

### Phase 6: Polish

1. Port documentation from `docs/`
2. Final README, CLAUDE.md, ARCHITECTURE.md updates
3. Verify both modes work end-to-end
4. Clean up any dead code

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

New modules wire in as follows:

| New Module | Where in Pipeline | Integration Detail |
|---|---|---|
| `sprite_extractor` | Inside `extract_assets` | After asset manifest built, scan for spritesheet .meta files |
| `mesh_splitter` | Inside `convert_scene` | When MeshRenderer has `len(m_Materials) > 1`, split before creating RbxParts |
| `vertex_color_baker` | Between `convert_materials` and `upload_assets` | After materials mapped, bake vertex colors for meshes that need it |
| `scriptable_object_converter` | Inside `transpile_scripts` | After C# transpilation, also convert .asset files to ModuleScripts |
| `bridge_injector` | Inside `write_output` | After scripts added to RbxPlace, scan Luau and inject bridge modules |
| `code_validator` | Inside `write_output` | After `luau_validator.validate_and_fix()`, run structural validation |
| `rbxl_binary_writer` | Inside `write_output` | After .rbxlx written, optionally convert to binary .rbxl |
| `report_generator` | End of `write_output` or new phase | Generate JSON report from ConversionContext stats |

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
Phase 1 (docs + entry points — no code deps):
  README, CLAUDE.md, ARCHITECTURE.md, convert_interactive.py, .claude/skills/

Phase 2 (standalone modules — all parallelizable):
  2.1 bridge_injector (depends on 2.8 for bridge file paths)
  2.2 vertex_color_baker
  2.3 sprite_extractor
  2.4 mesh_splitter
  2.5 scriptable_object_converter
  2.6 rbxl_binary_writer
  2.7 report_generator
  2.8 bridge Luau files (no code deps)

Phase 3 (pipeline integration — depends on Phase 2):
  All wiring into pipeline.py

Phase 4 (reconciliation — can overlap with Phase 3):
  4.1 api_mappings (independent)
  4.2 material_mapper (largest effort, independent)
  4.3 code_transpiler (depends on 4.1 for API_CALL_MAP)
  4.4 animation_converter (independent)
  4.5 luau_validator patterns (independent)
  4.6 ui_translator (independent)

Phase 5 (tests — do alongside each phase)

Phase 6 (polish — last)
```

---

## Risk Areas

| Risk | Mitigation |
|---|---|
| `Physics.lua` vs `physics_bridge.luau` — different API surfaces | Compare carefully; may need to keep both or merge into superset |
| `AnimatorBridge.lua` vs `animator_runtime.luau` — different animation approaches | Source uses config-table-driven state machines; dest uses TweenService. May need to support both |
| Binary writer integration — dest uses Luau Execution API for headless publishing | Binary writer is complementary (for direct Open Cloud upload). Both should coexist |
| `conversion_helpers.py` decomposition — 2087 LOC of orchestration logic | Most already exists in dest's scene_converter + component_converter. Only port the 3-4 functions that don't exist |
| Test count growth (source ~1200 + dest ~950) | Run full suite incrementally; fix failures as they arise |
| Import path changes — source uses flat `modules.X`, dest uses `converter.X`, `unity.X`, `roblox.X` | Systematic find-replace during each port step |

---

## Success Criteria

- [ ] Both `python u2r.py convert ...` and `/convert-unity ...` produce correct .rbxlx output
- [ ] All existing dest tests pass (947+)
- [ ] All ported source tests pass
- [ ] README clearly documents both modes with examples
- [ ] CLAUDE.md accurately describes the merged architecture
- [ ] New modules (bridge_injector, vertex_color_baker, sprite_extractor, mesh_splitter, scriptable_object_converter, rbxl_binary_writer) are integrated and tested
- [ ] Runtime Luau files from both repos coexist in `runtime/`
- [ ] Interactive mode supports resume via `.convert_state.json`
