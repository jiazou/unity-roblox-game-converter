# Phase 4: Reconcile Shared Modules — Detailed Plan

> Referenced from [MERGE_PLAN.md](MERGE_PLAN.md) Phase 4.  
> Each sub-section is a self-contained work item with acceptance criteria.

---

## Overview

Phase 4 reconciles 7 modules that exist in both repos. The guiding principle: **keep the dest's architecture and types, port the source's missing capabilities.** Every ported capability must conform to the dest's `core/roblox_types.py` and `core/unity_types.py` type system.

### Effort Summary

| Module | Complexity | Approach | Estimated Diff |
|--------|-----------|----------|---------------|
| 4.1 api_mappings | Low | Union merge | +50 lines |
| 4.2 material_mapper | **High** | Feature port into dest scaffold | +600 lines |
| 4.3 code_transpiler | Medium | Port prompt engineering + context building | +150 lines |
| 4.4 luau_validator | Low | Port unique patterns | +80 lines |
| 4.5 animation_converter | **High** | Dual-backend + transform-only pipeline + root motion wiring | +500 lines |
| 4.6 ui_translator | Medium | Port missing capabilities + layout (⚠ Y-inversion audit) | +120 lines |
| 4.7 scene_parser | Low | Diff for edge cases + `unity_yaml_utils` classID parity | +50 lines |

---

## 4.1 api_mappings — Union Merge

### Current State

| | Source | Dest |
|---|---|---|
| LOC | 492 | 1,002 |
| API_CALL_MAP entries | 278 | 611 |
| TYPE_MAP entries | 59 | 80+ |
| LIFECYCLE_MAP entries | 18 | 15+ |
| SERVICE_IMPORTS entries | 18 | 18+ |
| UTILITY_FUNCTIONS | — | 30+ (mathLerp, linqWhere, etc.) |

### Assessment

Dest is a strict superset in structure (it adds `UTILITY_FUNCTIONS`, which source lacks entirely). But source contains entries dest may be missing across several mapping families: NavMesh, new Input System, LINQ, TextMeshPro, Terrain, 2D physics, Application/Resources/Addressables, Invoke/WaitUntil/WaitWhile, DOTween, Cinemachine, and async/await patterns.

### Steps

1. **Extract unique source entries.** For each dict (`API_CALL_MAP`, `TYPE_MAP`, `LIFECYCLE_MAP`, `SERVICE_IMPORTS`), diff keys between source and dest. Identify source-only keys.
2. **Validate source-only entries.** Some source mappings may use guidance comments (e.g., `"DOTween.To": "-- Use TweenService:Create(...)"`). Ensure these still make sense in the dest's transpiler context where `UTILITY_FUNCTIONS` are auto-injected.
3. **Add source-only entries** to dest's dicts. Preserve dest's existing entries verbatim (don't reword).
4. **Dedup.** If both repos map the same key with different values, keep dest's unless source is strictly more accurate.

### Acceptance Criteria

- [ ] All source-only keys present in dest
- [ ] No duplicate keys
- [ ] Existing dest entries unchanged
- [ ] `UTILITY_FUNCTIONS` untouched (source has no equivalent)

### Dependencies

None — fully independent.

---

## 4.2 material_mapper — Feature Port (Largest Effort)

### Current State

| | Source | Dest |
|---|---|---|
| LOC | 1,734 | 727 |
| Supported shaders | 15+ (Standard, Legacy Diffuse/Specular/Bumped, Particle premultiply/multiply, URP, HDRP heuristic, Unlit/Mobile/Skybox, custom w/ companion scripts) | 6 (Standard, Standard Specular, URP/Lit, URP/SimpleLit, Lit, SimpleLit) |
| Texture operations | 7 real ops (copy, extract_channel w/ optional invert, bake_ao, threshold_alpha, pre_tile, composite_detail, blend_normal_detail, heightmap_to_normal; `to_grayscale` for emissive masks; resize is implicit in other ops) | 4 (copy, extract_r, extract_a, invert_a) |
| Unconverted tracking | Yes (severity levels + workarounds) | No |
| Vertex color detection | Yes (feeds vertex_color_baker) | No |
| Return type | `MaterialMapResult` (custom) | `dict[str, MaterialMapping]` |
| YAML parsing | PyYAML only | PyYAML + regex fallback for old formats |

### Assessment

The dest has cleaner types (`MaterialMapping` dataclass integrates with `scene_converter.py` and `rbxlx_writer.py`) and a dual YAML parsing strategy. But the source handles 3× more shaders and 2.5× more texture operations. This is the highest-risk reconciliation because material fidelity directly affects visual output quality.

### Steps

#### 4.2.1 Port Shader Identification

Source classifies shaders via `_identify_shader()` with a `ShaderInfo` dataclass and `_CUSTOM_SHADER_PATTERNS` regex table. Dest uses a `_SUPPORTED_SHADERS` frozenset.

**Action:** Expand dest's shader handling:
1. Add a `ShaderCategory` enum to dest: `BUILTIN`, `URP`, `HDRP`, `LEGACY`, `PARTICLE`, `SPRITE`, `UI`, `UNLIT`, `MOBILE`, `SKYBOX`, `CUSTOM`, `UNKNOWN`.
2. Port source's shader identification patterns into dest's `_identify_shader()` (or equivalent). Map each shader to its category + transparency + vertex-color flags.
3. **Important:** Source does NOT fall back to Standard-like extraction for unknown shaders. `_identify_shader()` returns `unknown`, and `_convert_material()` returns no `roblox_def`. Decide whether dest should add a fallback or preserve source's strict behavior.

**Shaders to add (verified in source):**
- Legacy Diffuse/Specular/Bumped variants
- Particle premultiply/multiply variants
- HDRP heuristic detection
- Unlit/Mobile/Skybox variants
- Data-driven custom shader detection via `_CUSTOM_SHADER_PATTERNS` regex + companion script resolution
- **Note:** The earlier plan listed `Particles/Standard Surface`, `Sprites/Diffuse`, `UI/Default Font`, `Nature/Tree Soft Occlusion` — these are NOT explicitly enumerated in source. Source handles them via category heuristics, not named entries.

#### 4.2.2 Port Texture Operations

Source defines 10 texture operation types via a `TextureOperation` dataclass with a deferred execution model.

**Action:** Add missing operations to dest's `TextureOperation`. Note: source's ops are not all standalone — `invert` is a parameter on `extract_channel`, and `resize` happens implicitly inside other ops. The real discrete operations to port:

| Operation | What It Does | When It Fires |
|---|---|---|
| `extract_channel` | Extracts R/G/B/A channel, with optional invert flag | Metallic (R), Smoothness→Roughness (A, inverted) |
| `bake_ao` | Multiplies AO map into color map | Shader has `_OcclusionMap` |
| `threshold_alpha` | Converts smooth alpha to binary cutout | Alpha cutout mode detected |
| `pre_tile` | Repeats texture at Unity's tiling scale | Tiling > (1,1) detected |
| `to_grayscale` | Converts to grayscale for emissive mask generation | Emissive mask needed (NOT metalness/roughness) |
| `composite_detail` | Blends detail albedo into main color (detail-mask-aware) | `_DetailAlbedoMap` present |
| `blend_normal_detail` | Blends detail normal into main normal | `_DetailNormalMap` present |
| `heightmap_to_normal` | Generates normal map from heightmap | `_ParallaxMap` present, no `_BumpMap` |

Each operation is a pure function: `(input_image, params) → output_image`. Port as individual functions in a new `texture_ops.py` helper or inline in `material_mapper.py`.

#### 4.2.3 Port Unconverted Feature Tracking

Source tracks `UnconvertedFeature` per material with severity (LOW/MEDIUM/HIGH), workarounds, and generates `UNCONVERTED.md`.

**Action:**
1. Add an `UnconvertedFeature` dataclass to dest (or add a `warnings` list to `MaterialMapping` if one doesn't exist — dest already has `warnings: list`).
2. Port `_generate_unconverted_md()` to produce a human-readable report of what couldn't be converted.
3. Wire into the report generator (Phase 3's `report_generator.py`).

#### 4.2.4 Port Additional Material Capabilities

Source has several capabilities the earlier draft missed entirely:
- **Specular-to-metallic approximation** — converts Standard (Specular) workflow to metallic values
- **Emission tint/strength extraction** — proper `_EmissionColor` parsing with intensity separation
- **Normal-scale baking** — applies `_BumpScale` to normal map intensity
- **Texture offset handling** — respects `_MainTex_ST` offset (not just tiling)
- **Companion Luau scripts** — generates per-material helper scripts for runtime property adjustment
- **`referenced_guids` filtering** — only processes materials actually referenced by the scene, not all materials in the project
- **Aggregate outputs** — `MaterialMapResult` carries `generated_textures`, `companion_scripts`, `unconverted_md_path`, and per-category conversion counts

**Action:** Port each capability. The companion Luau scripts and `referenced_guids` filtering are the highest-value items — they reduce asset bloat and enable runtime material adjustment.

#### 4.2.5 Port Vertex Color Detection

Source's `ShaderInfo.uses_vertex_colors` flag feeds into `vertex_color_baker.py` (Phase 2 module).

**Action:** During shader identification, set a `uses_vertex_colors` flag on `MaterialMapping` (add field if needed). The vertex color baker (already ported in Phase 2) reads this flag.

#### 4.2.6 Validate Integration

After all ports:
1. Confirm `MaterialMapping` still works with `scene_converter.py` (check field access patterns).
2. Confirm `MaterialMapping` still works with `rbxlx_writer.py` (check texture path references).
3. Run existing dest material tests + any new tests for ported shaders.

### Acceptance Criteria

- [ ] All 15+ source shader categories recognized and classified
- [ ] All 8 discrete texture operations available
- [ ] `UNCONVERTED.md` generated for materials with unconvertible features
- [ ] Vertex color flag propagated to vertex_color_baker
- [ ] Dest's `MaterialMapping` type unchanged or only extended (no breaking changes)
- [ ] Dest's dual YAML parsing (PyYAML + regex fallback) preserved
- [ ] Existing dest material tests still pass

### Dependencies

- Phase 2: `vertex_color_baker.py` must be ported first (for vertex color flag consumption).
- 4.1 is independent but nice-to-have (API mappings don't affect materials).

---

## 4.3 code_transpiler — Port Prompt Engineering

### Current State

| | Source | Dest |
|---|---|---|
| LOC | 988 | 2,083 |
| Strategy | AI-only (Claude) | Dual: rule-based (600+ regex patterns) + AI fallback |
| Concurrency | Sequential | ThreadPoolExecutor (up to 10 concurrent) |
| Dependency ordering | Yes (topological sort, dependency Luau as context) | Not evident |
| Caching | File-based (transpile_cache_dir) | SHA256-based |
| Pattern analysis | 6 warning categories (inheritance, LINQ, networking, generics, pooling, async) | Preprocessing (multiline, conditionals, out params, null-coalescing) |
| Confidence scoring | LLM-judged | Pattern match ratio |

### Assessment

Dest is architecturally stronger (concurrent execution, dual strategy, preprocessing pipeline). Source is stronger in **context quality** — it feeds dependency Luau and project context to the AI, and performs structural C# analysis to warn about hard-to-transpile patterns.

### Steps

#### 4.3.1 Port Dependency-Aware Context Building

Source's key advantage: `_build_dependency_graph()` + `_topological_sort()` + `_build_project_context()`. Each script's AI prompt includes concrete Luau of already-transpiled dependencies.

**Action:**
1. Add `_build_dependency_graph(script_infos)` to dest — analyzes class references (NOT `using` directives — source uses class name references, not imports) to build a DAG.
2. Add `_topological_sort(graph)` — source uses DFS with arbitrary cycle breaking, not Kahn's algorithm. Port source's actual implementation.
3. Modify dest's AI transpilation path to process scripts in dependency order.
4. When building the AI prompt for script N, include the Luau output of already-transpiled dependencies plus transitive signatures (source's scoped context building).
5. Port large-project manifest fallback — when project is too large for full context, source builds a condensed manifest instead.

**Constraint:** Must not break dest's concurrent execution. Solution: batch scripts by dependency level. Scripts at the same level (no inter-dependencies) can still run concurrently; only cross-level ordering is enforced.

#### 4.3.2 Port C# Pattern Analysis

Source's `_analyze_csharp_patterns(source)` detects 6 categories of hard-to-transpile constructs and adds targeted warnings.

**Action:** Add as a pre-analysis step in dest's transpilation pipeline. Before sending to AI or rule-based, run pattern analysis. Use results to:
- Add warnings to `TranspiledScript.warnings`
- Optionally inject additional context into the AI prompt (e.g., "This script uses LINQ extensively — ensure all LINQ operations use the provided utility functions")

Patterns to port:
| Pattern | Detection | Impact |
|---|---|---|
| Custom inheritance | Class extends non-MonoBehaviour | Warn: inherited methods not included |
| LINQ usage | Any LINQ method call (warns on any occurrence, not threshold-based) | Warn: complex data pipelines |
| Networking | `[Command]`, `[ClientRpc]`, `[SyncVar]`, and additional networking attributes | Warn: no Roblox networking equivalent |
| Nested generics | `Dictionary<string, List<T>>` | Warn: type erasure in Luau |
| Object pooling | Pool/pooling patterns | Warn: Roblox uses Instance caching differently |
| async/await | `async Task` pattern detection | Warn: map to coroutines carefully |

#### 4.3.3 Port Prompt Engineering Details

Source's AI prompt includes detailed rules not present in dest:
- Inspector config wiring instructions
- Property metamethod guidance
- Bridge-module import patterns (`AnimatorBridge`, etc.)
- Binary serialization rewrite rules
- Explicit `UNCONVERTED` stub generation for unhandled patterns
- `require()` validation (ensures generated requires point to real modules)
- Editor/test script exclusion heuristics

**Action:** Compare dest's AI prompt with source's. Port the prompt rules that improve transpilation quality. These are the "secret sauce" of the source's AI approach.

**Note on script type classification:** Source's `_classify_script_type()` has client-indicator tables (Camera.main, Input, etc.) but currently only returns `Script` or `ModuleScript` — it never returns `LocalScript` despite the detection logic. If dest already handles LocalScript classification, this is a non-issue. If not, the source logic can be completed during porting.

### Acceptance Criteria

- [ ] Scripts transpiled in dependency order (batched by level for concurrency)
- [ ] Each AI prompt includes dependency Luau context
- [ ] C# pattern warnings propagated to `TranspiledScript.warnings`
- [ ] Dest's rule-based strategy unaffected
- [ ] Dest's concurrent execution preserved (batched by dependency level)
- [ ] Existing dest transpiler tests still pass

### Dependencies

- None hard. The source's AI prompt does NOT inject `API_CALL_MAP` directly, so 4.1 is not a prerequisite. However, completing 4.1 first is still beneficial for consistency if the dest's transpiler references the mapping table.

---

## 4.4 luau_validator — Port Unique Patterns

### Current State

| | Source (code_validator) | Dest (luau_validator) |
|---|---|---|
| LOC | 340 | 7,477 |
| Fix categories | 5 (block balance, C# residue, parens, braces, method completeness) | 22 major fix functions |
| Error codes | E001–E030, W001–W031 | — (applies fixes, returns list of fix descriptions) |
| Approach | Report-only (returns ValidationResult) | Fix-and-report (returns fixed source + fix list) |

### Assessment

Dest is vastly more comprehensive (22× the code). It auto-fixes issues rather than just reporting them. Source's unique value is limited to a few specific checks dest may lack.

### Steps

1. **Diff source's checks against dest's 22 categories.** For each source check, find the dest equivalent:

   | Source Check | Dest Equivalent | Gap? |
   |---|---|---|
   | Block keyword balance (`function`/`if`/`for`/`while`/`repeat` vs `end`/`until`) | `_fix_missing_ends_in_blocks`, `_remove_excess_end_keywords`, `_fix_missing_function_end` | **No** — dest handles this with auto-fix |
   | C# residue (`using`, `class`, `namespace`, access modifiers, braces, semicolons, `new`) | `_fix_csharp_remnants` | **No** — dest strips these |
   | Parenthesis/bracket balance | `_fix_structural_syntax` | **No** |
   | Curly braces (distinguish C# blocks from Luau tables) | `_fix_csharp_remnants` + `_fix_structural_syntax` | **No** |
   | **Method completeness** (`check_method_completeness`) | **No direct equivalent** | **Yes** — port this |
   | Ternary if detection (don't flag `if...then...else` on one line) | `_fix_ternary_in_line` | **No** — dest already converts these |

2. **Port `check_method_completeness()`.** This compares C# method names against Luau function definitions and checks for `-- UNCONVERTED` / `-- TODO` comments as intentional coverage markers. Useful as a post-validation audit.
   - Add as a new function in dest's `luau_validator.py`.
   - Call after `validate_and_fix()` to produce warnings (not fixes — this is diagnostic).
   - Return list of missing method names for the conversion report.

3. **Consider porting the structured reporting model.** Source returns `ValidationIssue` objects with line, column, severity, and stable error/warning codes (E001–E030, W001–W031). Dest currently returns fix descriptions as plain strings. The structured model is valuable for:
   - Machine-readable validation reports
   - Consistent error codes across runs
   - Line-level precision for flagging issues in the conversion report
   
   **Action:** Evaluate whether dest's report generator or interactive mode would benefit from structured validation data. If yes, add `ValidationIssue` and `ValidationResult` types and have `check_method_completeness()` return them.

4. **Check source's comment/string stripping logic.** Source has a `_strip_comments_and_strings()` helper to avoid false positives. Verify dest has equivalent logic in its pattern matching. If dest does regex matching on raw source without stripping, port the stripping utility.

### Acceptance Criteria

- [ ] `check_method_completeness()` available in dest
- [ ] Comment/string stripping verified in dest (no false positives on commented-out C# code)
- [ ] Existing dest validator tests still pass

### Dependencies

None — fully independent.

---

## 4.5 animation_converter — Dual-Backend Support (High Complexity)

### Current State

| | Source | Dest |
|---|---|---|
| LOC | 1,236 | 1,335 |
| Runtime approach | Config-table driven (`AnimatorBridge.lua`) | TweenService sequences + state machine scripts |
| Blend tree support | Yes (1D) | No |
| Root motion | Yes (`extract_fbx_root_motion`) | No |
| Bone mapping | `UNITY_TO_R15_BONE_MAP` (humanoid) | Not evident |
| State machine | Config tables consumed by runtime | Inline Luau state machine (self-contained) |
| Output format | ModuleScript config tables + runtime bridge | Standalone Script with TweenService code |
| Controller parsing | `.controller` YAML → `AnimatorControllerData` | `.controller` YAML → `AnimatorController` |
| Clip parsing | `.anim` YAML → `AnimationClipInfo` | `.anim` YAML → `AnimClip` |
| JSON export | No | Yes (`export_controller_json`, `export_clip_keyframes`) |

### Assessment

These are fundamentally different animation strategies:

- **Source approach:** Generates lightweight config tables; heavy lifting happens in the `AnimatorBridge.lua` runtime. Supports blend trees (1D only) and has root motion helper code. Also has a **separate Legacy Animation / transform-only pipeline** (`convert_transform_animations()`) that scans scenes, prefabs, and standalone `.anim` files — this is entirely missing from the plan's original analysis.
- **Dest approach:** Generates self-contained TweenService scripts. No runtime dependency. Simpler for basic animations but can't handle blend trees or root motion.

Neither is strictly better. The right choice depends on animation complexity.

**Key corrections from code audit:**
- Root motion is **unintegrated helper code** — `extract_fbx_root_motion()` and `generate_root_motion_config()` exist but are never called by `convert_animations()` or `convert_transform_animations()`. They depend on `assimp` and `Hips`-named FBX channels.
- Blend tree resolution uses `m_Motion` file references to separate YAML docs with `m_Childs` / `m_BlendType`, NOT `m_BlendTree` as a direct field.
- `UNITY_TO_R15_BONE_MAP` is only used to **reject** humanoid clips from transform-only conversion, not to remap keyframes to R15 parts.
- Only the **base animator layer** is parsed; additional layers are ignored.
- Clips are resolved by **filename search**, not GUID lookup.

### Steps

#### 4.5.0 Port Legacy Animation / Transform-Only Pipeline

The plan's original analysis missed this entirely. Source has a complete separate pipeline for non-Animator animations:
- `is_transform_only_anim()` — detects clips that only animate position/rotation/scale (no bones)
- `convert_transform_animations()` — scans scenes, prefabs, and standalone `.anim` files for transform-only clips
- `generate_transform_anim_config()` — generates Luau config tables for `TransformAnimator` runtime

**Action:** Port this pipeline. It handles a common case (door animations, moving platforms, rotating objects) that the Animator pipeline doesn't cover.

#### 4.5.1 Port Root Motion Extraction (Unintegrated — Requires Wiring)

Root motion helpers exist in source but are **never called** by any pipeline entry point. They are aspirational code.

**Action:**
1. Port `FbxRootMotion` dataclass and `extract_fbx_root_motion()` to dest.
2. **Actually wire them in** — source never did this. Add root motion extraction to the animation pipeline when `apply_root_motion` is true on an Animator component.
3. Generate a root motion application script (source's `generate_root_motion_config()` adapted to dest's output style).
4. Note: requires `assimp` (optional dependency) and assumes root bone is named `Hips`.

#### 4.5.2 Port Blend Tree Support

Blend trees are a source-only capability. They require the config-table + runtime approach because TweenService can't interpolate between multiple animations based on a parameter.

**Action:**
1. Port `BlendTree` and `BlendTreeEntry` dataclasses to dest.
2. Add blend tree parsing to dest's `parse_controller_file()` — resolve via `m_Motion` file references to separate YAML documents containing `m_Childs` / `m_BlendType` (NOT a direct `m_BlendTree` field on the state).
3. When a blend tree is detected, switch that animator to the config-table backend (see 4.5.4).
4. Note: only 1D blend trees are supported; 2D blend trees are out of scope.

#### 4.5.3 Port R15 Bone Mapping

Source's `UNITY_TO_R15_BONE_MAP` maps Unity Humanoid bone names to Roblox R15 parts. However, in source it is only used as a **rejection filter** — clips targeting humanoid bones are excluded from transform-only conversion. It is NOT used to remap keyframes to R15 parts.

**Action:** Port the bone mapping dict to dest. Current use: rejection filter for transform-only pipeline. Future use: could enable actual humanoid keyframe remapping (new capability neither repo has).

#### 4.5.4 Implement Backend Selection

**Action:** Add a backend selection heuristic:

```
IF controller has blend trees OR controller has >5 parameters:
    → Config-table backend (source approach)
    → Requires AnimatorBridge runtime (ported in Phase 2)
ELSE:
    → TweenService backend (dest approach)
    → Self-contained, no runtime dependency
```

Implementation:
1. Add a `backend: Literal["tween", "config_table"]` field to the animation conversion result.
2. In `convert_animations()`, analyze each controller's complexity before choosing backend.
3. Config-table backend: use source's `generate_animator_config()` adapted to dest's types.
4. TweenService backend: use dest's existing `generate_tween_script()` / `generate_state_machine_script()`.

#### 4.5.5 Reconcile Data Structures

Source and dest parse the same YAML but into different dataclasses. Since dest's types integrate with `core/unity_types.py`, keep dest's dataclasses and extend them:

| Source Type | Dest Type | Extension Needed |
|---|---|---|
| `AnimationClipInfo` | `AnimClip` | Add `bone_paths: list[str]` if missing |
| `AnimatorControllerData` | `AnimatorController` | Add `blend_trees: dict[str, BlendTree]` |
| `AnimatorState` (with blend_tree) | `AnimState` | Add `blend_tree: BlendTree | None` |
| `StateTransition` | `AnimTransition` | Verify condition fields match |
| `AnimatorParameter` | `AnimParameter` | Verify type enum matches |
| `FbxRootMotion` | (new) | Add to dest |

#### 4.5.6 Validate Both Backends

Test matrix:
| Scenario | Expected Backend | Key Validation |
|---|---|---|
| Simple position tween (1 clip, no controller) | TweenService | Keyframes play correctly |
| Transform-only .anim (door/platform) | Transform-only pipeline | TransformAnimator runtime drives movement |
| State machine (3 states, Bool transitions) | TweenService | State transitions fire on parameter change |
| Blend tree (1D, walk/run blend) | Config-table | Blending interpolates based on parameter |
| Root motion (character locomotion) | Config-table | Character moves with animation (newly wired) |
| Complex controller (>5 params, blend trees + transitions) | Config-table | Full state machine works |

### Acceptance Criteria

- [ ] Legacy Animation / transform-only pipeline ported and working
- [ ] Root motion extraction ported AND wired into pipeline (source had it unwired)
- [ ] Blend tree parsing added to controller parser (via `m_Motion` refs, not `m_BlendTree`)
- [ ] R15 bone mapping available (currently: rejection filter; future: keyframe remapping)
- [ ] Backend selection heuristic implemented and documented
- [ ] TweenService backend (dest's existing) still works for simple animations
- [ ] Config-table backend (source's approach) works for complex animations
- [ ] Both backends produce valid Luau that runs in Roblox Studio
- [ ] Existing dest animation tests still pass

### Dependencies

- Phase 2: `AnimatorBridge.luau` runtime must be ported first (config-table backend needs it).
- Independent of 4.1–4.4.

---

## 4.6 ui_translator — Port Missing Elements & Layout

### Current State

| | Source | Dest |
|---|---|---|
| LOC | 600 | 526 |
| Entry point | `translate_ui_hierarchy(scene_nodes)` | `convert_canvas(canvas_nodes)` |
| Return type | `UITranslationResult` (custom) | `list[RbxScreenGui]` (from `core/roblox_types`) |
| CanvasScaler handling | No | Yes (3 scale modes, reference resolution) |
| Button callbacks | No | Yes (method names stored as attributes) |
| Font mapping | Yes (Arial, Roboto → Roblox equivalents) | Not evident |
| Supported types | Text, Image, Button, Canvas, ScrollRect, Layout groups, Slider/Toggle (as Frame) | Text, Image, Button, InputField, Canvas, ScrollRect, Layout groups, Slider/Dropdown (as Frame) |

### Assessment

Both handle the core UI elements. Source has font mapping and slightly richer property extraction. Dest has CanvasScaler handling and button callback tracking. Mostly complementary.

### Steps

#### 4.6.1 Port Font Mapping

Source maps Unity font names to Roblox `Enum.Font`:

| Unity Font | Roblox Font |
|---|---|
| Arial | `Enum.Font.Arial` |
| Roboto | `Enum.Font.Roboto` (with bold variant support) |
| (default) | `Enum.Font.SourceSans` |

**Note:** The earlier draft incorrectly claimed Roboto → Gotham. Source maps Roboto to Roboto.

**Action:** Add font mapping to dest's text property extraction. When `m_Font` or `m_FontAsset` is present, resolve to Roblox font enum.

#### 4.6.2 Port TextAnchor → Alignment Mapping

Source has a 9-point mapping from Unity `TextAnchor` enum to Roblox `TextXAlignment` + `TextYAlignment`:

```
UpperLeft   → Left, Top       UpperCenter → Center, Top       UpperRight  → Right, Top
MiddleLeft  → Left, Center    MiddleCenter→ Center, Center    MiddleRight → Right, Center
LowerLeft   → Left, Bottom    LowerCenter → Center, Bottom    LowerRight  → Right, Bottom
```

**Action:** Verify dest handles this. If not, add the mapping.

#### 4.6.3 Port Sprite GUID Detection for Images

Source's behavior is more nuanced than initially described:
- Nodes that remain `Frame` (no Image component) with no sprite → solid-color `Frame` with BackgroundColor
- Explicit `Image` components always classify as `ImageLabel` (even with empty `image` field)
- MonoBehaviour GUID fallback: if a component isn't recognized, source checks if it's a UI Image via MonoBehaviour GUID

**Action:** Verify dest handles the MonoBehaviour GUID fallback for UI Image detection. This matters for projects using custom Image subclasses.

#### 4.6.4 Diff Element Types

Compare supported UI component types:

| Component | Source | Dest | Action |
|---|---|---|---|
| Text (no TMP in source `_UI_TYPE_MAP`) | TextLabel | TextLabel | — |
| Image/RawImage | ImageLabel | ImageLabel | — |
| Button | TextButton | TextButton | — |
| InputField (no TMP_InputField in source) | Not supported | TextBox | — |
| Toggle | Frame (warning) | TextButton | Keep dest's (better) |
| Slider | Frame (warning) | Frame | — |
| Dropdown | Not supported | Frame | — |
| ScrollRect | ScrollingFrame | ScrollingFrame | — |
| VerticalLayoutGroup | UIListLayout | UIListLayout | — |
| HorizontalLayoutGroup | UIListLayout | UIListLayout | — |
| GridLayoutGroup | UIGridLayout | UIGridLayout | — |
| ContentSizeFitter | Not supported | Noted | — |

No source-only element types. Dest is equal or better for every type.

#### 4.6.5 Port Additional Source-Only Capabilities

Source has capabilities not in the original plan:
- **Layout-group alignment/spacing translation** — converts Unity child alignment enums to Roblox HorizontalAlignment/VerticalAlignment + padding
- **Active-state → `Visible`** — maps `m_IsActive` to Roblox `Visible` property
- **Conversion helpers into `rbxl_writer` types** — `to_rbx_ui_element()` and `to_rbx_screen_gui()` bridge the translator's output to the writer's input format

**Action:** Port these. The `rbxl_writer` bridge functions may not be needed if dest's type system (`RbxScreenGui`, `RbxUIElement`) already integrates with the writer.

#### 4.6.6 Port Partial Anchor Detection Warning

Source warns when a RectTransform uses mixed stretch + offset anchoring (e.g., `anchorMin.x ≠ anchorMax.x` but `anchorMin.y == anchorMax.y`). This produces layout that's hard to replicate exactly in Roblox.

**Action:** Add this warning to dest's RectTransform conversion.

#### 4.6.7 Y-Inversion Risk (Integration Warning)

**Critical:** Source inverts Y position and pivot in its RectTransform conversion, but the module header comment says "no GUI Y inversion is needed." This contradiction means porting the math blindly can vertically flip layouts. Before porting:
1. Read source's actual Y-inversion logic in `translate_rect_transform()`
2. Compare with dest's coordinate handling
3. Test with a real Unity Canvas to determine which is correct
4. Document the decision

### Acceptance Criteria

- [ ] Font mapping resolves Unity fonts to Roblox `Enum.Font`
- [ ] TextAnchor → TextXAlignment + TextYAlignment mapping complete
- [ ] Sprite-vs-solid-color distinction for Images
- [ ] Partial anchor warning emitted
- [ ] Existing dest UI tests still pass

### Dependencies

None — fully independent.

---

## 4.7 scene_parser — Edge Case Diff

### Current State

| | Source | Dest |
|---|---|---|
| LOC | 351 | 241 |
| Algorithm | 7-pass | 7-pass (identical structure) |
| Return type | `ParsedScene` (local) | `ParsedScene` (from `core/unity_types`) |
| Binary scene support | No | Yes (delegates to `binary_scene_parser.py`) |
| Referenced asset tracking | mesh + material + animator controller GUIDs | mesh + material GUIDs |

### Assessment

Both use the same 7-pass algorithm (index → stubs → transforms → components → hierarchy → prefabs → render settings). Dest adds binary scene support. Source tracks animator controller GUIDs.

### Steps

1. **Port animator controller GUID extraction.** Source extracts `referenced_animator_controller_guids` from Animator components (classID 95). Check if dest already does this. If not:
   - Add `referenced_animator_controller_guids: set[str]` to dest's `ParsedScene` type.
   - In Pass 4 (attach components), when an Animator component is found, extract the `m_Controller` GUID.
   - This feeds into the animation converter (4.5) for discovering which controllers to parse.

2. **Port skybox material detection.** Source extracts `skybox_material_guid` from RenderSettings. Verify dest does this in Pass 7.

3. **Port parse warning accumulation.** Source collects YAML parse errors into `parse_warnings: list[str]` instead of failing. Verify dest has equivalent resilience.

4. **Verify component classID coverage.** Source delegates most component coverage to `modules.unity_yaml_utils` via `KNOWN_COMPONENT_CIDS` and `COMPONENT_CID_TO_NAME` — validating parity from `scene_parser.py` alone is insufficient. Must also diff `unity_yaml_utils` against dest's equivalent. Key classIDs: Transform (4/224), MeshFilter (33), MeshRenderer (23), SkinnedMeshRenderer (137), Animator (95), Rigidbody (54), Collider (136), PrefabInstance (1001), RenderSettings (104), MonoBehaviour (114).

5. **Port unresolved-parent promotion behavior.** Source promotes nodes with unresolved parent Transforms to roots, which is especially important for prefab-owned objects. Verify dest handles this edge case identically.

6. **Port rich `ParsedScene` outputs.** Beyond GUIDs, source's `ParsedScene` carries `raw_documents`, merged `render_settings`, `parse_warnings`, and rich `prefab_instances` metadata (source prefab GUID/fileID, transform parent, modifications, removed components). Verify dest's `ParsedScene` type has equivalent fields.

### Acceptance Criteria

- [ ] Animator controller GUIDs tracked in `ParsedScene`
- [ ] Skybox material GUID extracted
- [ ] Parse warnings accumulated (no hard failures on bad YAML)
- [ ] All source classIDs handled
- [ ] Existing dest parser tests still pass

### Dependencies

None — fully independent. But completing this before 4.5 (animation) is helpful since the animation converter consumes `referenced_animator_controller_guids`.

---

## Execution Order

The sub-items have few hard dependencies between them. Recommended order optimizes for risk reduction (hardest first) and dependency satisfaction:

```
┌─────────────────────────────────────────────────────────┐
│ Can start immediately (no dependencies):                │
│   4.1 api_mappings        (Low, ~1hr)                   │
│   4.3 code_transpiler     (Medium, ~3hr)  [no hard dep] │
│   4.4 luau_validator      (Low, ~1hr)                   │
│   4.6 ui_translator       (Medium, ~2hr)  [⚠ Y-invert] │
│   4.7 scene_parser        (Low, ~1hr)                   │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ Start after Phase 2 + 4.7:                              │
│   4.2 material_mapper     (High, ~5hr)                  │
│        └─ needs vertex_color_baker from Phase 2         │
│        └─ nice-to-have: scene_parser GUID tracking      │
│   4.5 animation_converter (High, ~6hr)                  │
│        └─ needs AnimatorBridge.luau + TransformAnimator  │
│           from Phase 2                                   │
│        └─ nice-to-have: scene_parser controller GUIDs   │
│        └─ includes new transform-only pipeline (4.5.0)  │
└─────────────────────────────────────────────────────────┘
```

---

## Testing Strategy

Each reconciliation item should have:

1. **Existing dest tests pass** — run before and after. Zero regressions.
2. **Ported source test cases** — for capabilities that came from source, port the relevant test assertions (not the test scaffolding — adapt to dest's test structure).
3. **Integration smoke test** — after all 7 items complete, run a full pipeline conversion on a test Unity project to verify modules compose correctly.

---

## Risk Mitigations

| Risk | Mitigation |
|---|---|
| Material mapper port breaks `scene_converter` / `rbxlx_writer` integration | Add `MaterialMapping` field changes behind optional fields with defaults. Run integration test before merging. |
| Unknown shaders silently produce no `roblox_def` | Source does NOT fall back to Standard extraction for unknown shaders. Decide explicitly: add a fallback in dest, or preserve strict behavior and log a warning. |
| Animation dual-backend adds maintenance burden | Backend selection is deterministic (based on controller complexity). Document the heuristic clearly. Consider removing config-table backend later if TweenService proves sufficient. |
| Root motion code is unintegrated in source | Must be wired into pipeline during port — don't assume it works just because the functions exist. Add integration tests. |
| Only base animator layer parsed | Multi-layer support is out of scope. Document this limitation. May cause missing animations for controllers with override/additive layers. |
| UI Y-inversion contradiction | Source code inverts Y but header comment says no inversion needed. Must test with real Unity Canvas before porting math. Wrong choice flips all layouts vertically. |
| Dependency-ordered transpilation slows down concurrent execution | Batch by dependency level preserves concurrency within levels. Measure wall-clock time before/after. |
| `scene_parser` classID coverage split across two files | Must diff both `scene_parser.py` AND `unity_yaml_utils.py` against dest — checking only the parser misses delegated component coverage. |
| Union merge of api_mappings introduces conflicting entries | Keep dest's value when both repos map the same key differently. Log conflicts for manual review. |
