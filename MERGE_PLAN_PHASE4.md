# Phase 4: Reconcile Shared Modules — Detailed Plan

> Referenced from [MERGE_PLAN.md](MERGE_PLAN.md) Phase 4.  
> Each sub-section is a self-contained work item with acceptance criteria.

> **⚠ Phase 3 reconciliation pass applied 2026-04-24.** Several plan assumptions were invalidated by Phase 3 landed outcomes (see [inline-over-runtime-wrappers.md](https://github.com/jiazou/unity2rbxlx/blob/main/converter/docs/design/inline-over-runtime-wrappers.md) and [merge-plan-phase-3-augmented.md](https://github.com/jiazou/unity2rbxlx/blob/main/converter/docs/design/merge-plan-phase-3-augmented.md) in the dest repo). Key changes: §4.4 rewritten (the 7477-LOC `luau_validator.py` was deleted and replaced by a `luau-analyze` + AI reprompt loop); §4.5 rewritten (the dual-backend / `animator_bridge.luau` + `TransformAnimator.luau` injection model was rejected — those bridges were removed and their features consolidated into `animator_runtime.luau`); §4.2.4 companion-scripts clause replaced (contradicts the inline-over-runtime-wrappers policy); §4.2.5 split into schema-now / wiring-deferred. See **Phase 3 Reconciliation Log (2026-04-24)** at the end of this file for the full list.

---

## Overview

Phase 4 reconciles 7 modules that exist in both repos. The guiding principle: **keep the dest's architecture and types, port the source's missing capabilities.** Every ported capability must conform to the dest's `core/roblox_types.py` and `core/unity_types.py` type system. Ports must also honor the dest's **inline-over-runtime-wrappers** policy (adopted 2026-04-14): Unity APIs are translated at transpile time via `API_CALL_MAP` / `UTILITY_FUNCTIONS`, not by emitting per-script `require()` calls to runtime wrapper modules. New runtime modules are justified only when the Unity feature is a genuinely stateful subsystem (e.g., animator state machine, pathfinding).

### Cross-Cutting Constraints (from CEO + Codex review, 2026-04-12; updated per eng review; reconciled with Phase 3 outcomes 2026-04-24)

1. **Validation ordering:** All generated Luau that contains executable code (animation data modules with logic, ScriptableObject modules that expose functions, stub scripts) must pass the same `luau-analyze` syntax gate used by the transpiler before `write_output` finalizes. Pure data-table modules (controller keyframe exports, plain config dicts) are exempt — assert via a unit test that they contain no executable constructs. **Owner: 4.4** (now a diagnostic/reporting task, not a validator port — see §4.4). 4.4 must extend the existing `luau-analyze` invocation in `code_transpiler.py` to also cover generated scripts produced by 4.2/4.5 before they reach `rbx_place.scripts`.
2. **Asset ID substitution contract:** All modules that emit asset references (UI image GUIDs, material texture paths, animation clip references) must use a consistent GUID placeholder format (`rbxassetid://<unity-guid>`) that the upload phase can resolve in a single pass. Each module must not invent its own placeholder scheme. **Owner: 4.2** — material_mapper is the largest texture emitter. 4.2 must define the canonical format and add a test asserting all emitted asset references conform. Currently no module follows this contract (source uses local file paths for textures, `rbxassetid://{filename}` for uploads).
3. **Error resilience:** Every new codepath that processes external data (YAML, images, FBX) must handle corrupt/missing/unexpected input gracefully — log the failure, skip the item, record in UNCONVERTED.md. Never crash on bad input data. Applies to ALL modules equally — 4.5 and 4.6 need the same resilience criteria as 4.2 (see per-module acceptance criteria).
4. **Deterministic output (per eng review):** All module outputs must be deterministic across runs given the same input. Specifically: code_transpiler dependency cycle-breaking must use a stable sort (alphabetical by script name), not arbitrary dict ordering. Non-deterministic transpilation makes debugging impossible.
5. **Rollback strategy (per eng review):** Each 4.x item should be a separate PR with CI validation before merge into the dest. Tag a rollback point commit before Phase 4 begins. Run integration test checkpoints after 4.2 and 4.5 (the two High-complexity items) before proceeding to remaining items.
6. **Inline-over-runtime-wrappers policy (Phase 3 landed):** Ports must not emit per-script `require()` calls to new runtime wrapper modules reimplementing Unity APIs. Runtime modules are reserved for stateful subsystems (`animator_runtime.luau`, `nav_mesh_runtime.luau`, `event_system.luau`, `physics_bridge.luau`, `cinemachine_runtime.luau`). A regression test (`converter/tests/test_no_rejected_bridges.py`) guards the nine rejected bridges + `bridge_injector.py` from reappearing. If a ported source capability depends on a rejected bridge, re-home it to `api_mappings.UTILITY_FUNCTIONS` (inline helper) or to the relevant runtime module directly.

### Effort Summary

| Module | Complexity | Approach | Estimated Diff |
|--------|-----------|----------|---------------|
| 4.1 api_mappings | Low | Union merge | +50 lines |
| 4.2 material_mapper | **High** | Feature port into dest scaffold (companion-scripts clause dropped per inline policy) | +500 lines |
| 4.3 code_transpiler | Medium | Port prompt engineering + context building (syntax gate already in place via luau-analyze) | +150 lines |
| 4.4 (diagnostic) | Low | Post-transpile method-completeness audit feeding `report_generator` (not a validator port) | +60 lines |
| 4.5 animation_converter | **High** | Extend `animator_runtime.luau` data path (blend trees + controller richness); keep inline TweenService for simple/transform-only clips. No new runtime bridges. | +400 lines |
| 4.6 ui_translator | Medium | Port missing capabilities + layout (⚠ Y-inversion audit) | +120 lines |
| 4.7 scene_parser | Low | Diff for edge cases + `unity_yaml_utils` classID parity + `referenced_animator_controller_guids` field | +50 lines |

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
- [ ] **Ported mappings verified against runtime:** Each new `API_CALL_MAP` entry's target Roblox API or utility function is accessible in generated Luau — i.e., the required `SERVICE_IMPORTS` entry exists, or the target is a `UTILITY_FUNCTIONS` helper that gets auto-injected

### Dependencies

None — fully independent.

---

## 4.2 material_mapper — Feature Port (Largest Effort)

### Current State

| | Source | Dest (2026-04-24) |
|---|---|---|
| LOC | 1,734 | 783 |
| Supported shaders | 15+ (Standard, Legacy Diffuse/Specular/Bumped, Particle premultiply/multiply, URP, HDRP heuristic, Unlit/Mobile/Skybox, custom w/ companion scripts) | 10 entries in `_SUPPORTED_SHADERS` (Standard, Standard Specular, URP/Lit, URP/SimpleLit, Lit, SimpleLit, plus HDRP variants) |
| Texture operations | 7 real ops (copy, extract_channel w/ optional invert, bake_ao, threshold_alpha, pre_tile, composite_detail, blend_normal_detail, heightmap_to_normal; `to_grayscale` for emissive masks; resize is implicit in other ops) | 4 (copy, extract_r, extract_a, invert_a) |
| Unconverted tracking | Yes (severity levels + workarounds) | Partial (`warnings` list on `MaterialMapping`) |
| Vertex color detection | Yes (feeds vertex_color_baker) | No |
| Return type | `MaterialMapResult` (custom) | `dict[str, MaterialMapping]` |
| YAML parsing | PyYAML only | PyYAML + regex fallback for old formats |
| `referenced_guids` filtering | Yes | **Already landed** (Phase 3 — `map_materials()` filters by `referenced_guids` set) |

### Assessment

The dest has cleaner types (`MaterialMapping` dataclass integrates with `scene_converter.py` and `rbxlx_writer.py`) and a dual YAML parsing strategy. But the source handles 3× more shaders and 2.5× more texture operations. This is the highest-risk reconciliation because material fidelity directly affects visual output quality.

### Steps

#### 4.2.1 Port Shader Identification

Source classifies shaders via `_identify_shader()` with a `ShaderInfo` dataclass and `_CUSTOM_SHADER_PATTERNS` regex table. Dest uses a `_SUPPORTED_SHADERS` frozenset.

**Action:** Expand dest's shader handling:
1. Add a `ShaderCategory` enum to dest: `BUILTIN`, `URP`, `HDRP`, `LEGACY`, `PARTICLE`, `SPRITE`, `UI`, `UNLIT`, `MOBILE`, `SKYBOX`, `CUSTOM`, `UNKNOWN`. Add a `shader_category: ShaderCategory` field on `MaterialMapping` so downstream code (reporting, QA) can filter by category.
2. Port source's shader identification patterns into dest's `_identify_shader()` (or equivalent). Map each shader to its category + transparency + vertex-color flags.
3. **Unknown-shader fallback — formalize what the dest already does.** `material_mapper.py:222-229` currently accepts any shader and runs the full extraction with fallback texture slot names — that's already a de facto Standard fallback. The Phase 4 work is to **formalize and surface** it:
   - Extract the fallback path into a named `_apply_standard_fallback()` helper so it's grep-able and testable.
   - When `ShaderCategory == UNKNOWN` (including `Shader Graphs/*` and `Custom/*` which currently don't even warn), record an `UnconvertedFeature` entry with severity=LOW and message `"Unknown shader '{name}' — applied Standard fallback. Visual fidelity may differ; consider adding '{name}' to _SUPPORTED_SHADERS if the fallback looks wrong."` The current silent-on-custom-shader behavior hides real coverage gaps from the report.
   - Decision is settled by dest code (the fallback already exists). No separate CEO re-review needed against the 10-shader baseline.

**Shaders to add (verified in source):**
- Legacy Diffuse/Specular/Bumped variants
- Particle premultiply/multiply variants
- HDRP heuristic detection
- Unlit/Mobile/Skybox variants
- Data-driven custom shader detection via `_CUSTOM_SHADER_PATTERNS` regex + companion script resolution. **Note (per eng review):** Current patterns (CurvedUnlitAlpha, CurvedUnlitCloud, CurvedRotation, UnlitBlinking) are Trash Dash-specific. Per project CLAUDE.md rule ("game-specific fixes stay in output only, not converter"), these should be made configurable via a project-level config rather than hardcoded. Port the *mechanism* (regex table + companion script resolution), populate with general examples, allow per-project extension.
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

**Performance note (per eng review):** Port texture ops to accept `PIL.Image` instances, not file paths, so the caller opens once and pipes through multiple ops. Also, `pre_tile` must clamp `tile_x * tile_y` or compute target dimensions *before* allocating the tiled image — a 4K texture at 4× tiling allocates ~1GB before the max_res clamp kicks in.

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
- **Aggregate outputs** — `MaterialMapResult` carries `generated_textures`, `unconverted_md_path`, and per-category conversion counts

**Action:** Port each capability as static material data (extra fields on `MaterialMapping` or generated texture outputs). Do NOT emit per-material companion Luau scripts — they conflict with the inline-over-runtime-wrappers policy (adopted 2026-04-14). If a material property genuinely needs runtime adjustment (animated emission, scrolling UV), the adjustment belongs in the scene-level script that owns the part — not in a per-material require'd helper.

**Explicitly dropped from scope (vs earlier draft):**
- Per-material companion Luau scripts for runtime property adjustment.
- `companion_scripts` aggregate field on `MaterialMapResult`-equivalent output.

**Already landed (no work needed):**
- `referenced_guids` filtering — present in `map_materials()` and pipeline.py ~L750. Acceptance criterion below reframed as "preserve existing behavior."

#### 4.2.5 Vertex Color Detection — Schema (4.2.5a) vs Wiring (4.2.5b)

Source's `ShaderInfo.uses_vertex_colors` flag feeds into `vertex_color_baker.py`. In the dest, the baker is ported but **NOT wired** into the pipeline (per Phase 3 augmented plan item 2: deferred pending a test project with vertex-color-only materials).

**4.2.5a — schema (land in Phase 4):** During shader identification, set a `uses_vertex_colors: bool = False` field on `MaterialMapping`. Populate during `_identify_shader()`. Landing the schema now is cheap and unblocks future wiring without a downstream consumer change.

**4.2.5b — baker wiring (deferred post-Phase 4):** Wire `vertex_color_baker` into the pipeline between `convert_materials` and `convert_scene`, reading the `uses_vertex_colors` flag. Blocked on a test project that exercises vertex-color-only materials so the integration can be validated end-to-end. Track as a follow-up in `TODO.md`.

#### 4.2.6 Validate Integration

After all ports:
1. Confirm `MaterialMapping` still works with `scene_converter.py` (check field access patterns).
2. Confirm `MaterialMapping` still works with `rbxlx_writer.py` (check texture path references).
3. Run existing dest material tests + any new tests for ported shaders.

### Acceptance Criteria

- [ ] All 15+ source shader categories recognized and classified (dest currently has 10 in `_SUPPORTED_SHADERS`)
- [ ] All 8 discrete texture operations available
- [ ] `UNCONVERTED.md` generated for materials with unconvertible features
- [ ] `MaterialMapping.uses_vertex_colors: bool` field added and populated (4.2.5a). Wiring to `vertex_color_baker` (4.2.5b) is deferred.
- [ ] Dest's `MaterialMapping` type unchanged or only extended (no breaking changes)
- [ ] Dest's dual YAML parsing (PyYAML + regex fallback) preserved
- [ ] Existing dest material tests still pass
- [ ] **No new per-material runtime wrapper scripts emitted** — the inline-over-runtime-wrappers regression test (`converter/tests/test_no_rejected_bridges.py`) and any new assertions added for 4.2 must pass. Material data flows as static fields on `MaterialMapping` + generated textures only.
- [ ] **Idempotent under interactive prerequisite replay** — UNCONVERTED.md and generated texture outputs must not assume upload/resolve already ran (interactive mode skips cloud phases during replay)
- [ ] **Unknown shader fallback:** Unrecognized shaders produce a best-effort Standard-like `MaterialMapping` with a warning in UNCONVERTED.md, not a silent skip
- [ ] **Texture operation error resilience:** Every texture operation (`bake_ao`, `threshold_alpha`, `composite_detail`, etc.) gracefully handles missing/corrupt/channelless input images — skip the op, log the failure, record in UNCONVERTED.md. Never crash on bad image data. Specifically handle: missing file, LFS pointer, no alpha channel, unexpected channel count, oversized images.
- [ ] **Deterministic texture output names:** Generated textures (from bake_ao, composite_detail, etc.) use deterministic names derived from material name + operation, so re-runs produce identical output
- [ ] **`referenced_guids` filtering — already landed.** `map_materials()` in the dest already filters by `referenced_guids`. Phase 4 acceptance: preserve existing behavior; add a test asserting that in multi-scene mode `referenced_guids` is the union of all scenes' referenced material GUIDs, not per-scene.

### Dependencies

- Phase 2: `vertex_color_baker.py` must be ported first (for vertex color flag consumption). ✅ Done.
- 4.1 is independent but nice-to-have (API mappings don't affect materials).

---

## 4.3 code_transpiler — Port Prompt Engineering

### Current State

| | Source | Dest (2026-04-24) |
|---|---|---|
| LOC | 988 | 1,658 |
| Strategy | AI-only (Claude) | AI-first with `luau-analyze` syntax gate + AI reprompt loop (up to 2 retries) |
| Concurrency | Sequential | ThreadPoolExecutor (up to 10 concurrent) |
| Dependency ordering | Yes (topological sort, dependency Luau as context) | Not evident |
| Caching | File-based (transpile_cache_dir) | SHA256-based, invalidated on syntax error |
| Pattern analysis | 6 warning categories (inheritance, LINQ, networking, generics, pooling, async) | Preprocessing (multiline, conditionals, out params, null-coalescing) |
| Confidence scoring | LLM-judged | Pattern match ratio |
| Syntax validation | — | `luau-analyze` post-transpile (replaces the removed `luau_validator.py`) |

### Assessment

Dest is architecturally stronger (concurrent execution, dual strategy, preprocessing pipeline). Source is stronger in **context quality** — it feeds dependency Luau and project context to the AI, and performs structural C# analysis to warn about hard-to-transpile patterns.

### Steps

#### 4.3.1 Port Dependency-Aware Context Building

Source's key advantage: `_build_dependency_graph()` + `_topological_sort()` + `_build_project_context()`. Each script's AI prompt includes concrete Luau of already-transpiled dependencies.

**Action:**
1. Add `_build_dependency_graph(script_infos)` to dest — analyzes class references (NOT `using` directives — source uses class name references, not imports) to build a DAG.
2. Add `_topological_sort(graph)` — source uses DFS with arbitrary cycle breaking, not Kahn's algorithm. Port source's actual implementation. **Fix during port (per eng review):** Source's cycle-breaking is non-deterministic (depends on dict iteration order). Make it deterministic by sorting neighbors alphabetically before DFS. Add acceptance criterion: dependency ordering is identical across runs given the same input.
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
- Binary serialization rewrite rules
- Explicit `UNCONVERTED` stub generation for unhandled patterns
- `require()` validation (ensures generated requires point to real modules)
- Editor/test script exclusion heuristics

**Action:** Compare dest's AI prompt with source's. Port the prompt rules that improve transpilation quality. Do NOT port source's "bridge-module import patterns" rule (e.g., `require(AnimatorBridge)`) — those bridges were rejected by the inline-over-runtime-wrappers policy and the prompt must steer the AI toward inline translations via `api_mappings` / `UTILITY_FUNCTIONS` instead. For animator-specific needs, the prompt should point at the consolidated `animator_runtime.luau` module (the one remaining runtime).

**Note on script type classification (resolved per eng review):** Source's `_classify_script_type()` has client-indicator tables (Camera.main, Input, etc.) but currently only returns `Script` or `ModuleScript` — it never returns `LocalScript` despite the detection logic. **Action: resolve before implementation begins.** Diff dest's script classification against source's. If dest returns LocalScript for camera/input scripts, keep dest's behavior. If dest also lacks LocalScript classification, decide whether to complete the logic or keep the ModuleScript default. This is a design decision that affects the bootstrap architecture — do not leave it as "verify during porting."

### Acceptance Criteria

- [ ] Scripts transpiled in dependency order (batched by level for concurrency)
- [ ] Each AI prompt includes dependency Luau context
- [ ] C# pattern warnings propagated to `TranspiledScript.warnings`
- [ ] Dest's rule-based strategy unaffected
- [ ] Dest's concurrent execution preserved (batched by dependency level)
- [ ] Existing dest transpiler tests still pass
- [ ] **Dependency ordering and warnings persisted** (via script_manifest.json or conversion_context.json) so the preserved-script rehydration path doesn't lose them

### Dependencies

- None hard. The source's AI prompt does NOT inject `API_CALL_MAP` directly, so 4.1 is not a prerequisite. However, completing 4.1 first is still beneficial for consistency if the dest's transpiler references the mapping table.

---

## 4.4 Transpile Diagnostics — Method-Completeness Audit

> **Scope rewritten 2026-04-24.** The 7,477-LOC `luau_validator.py` assumed by the earlier draft was **deleted on 2026-04-18** (commit 594238c) and replaced by a `luau-analyze` + AI reprompt loop in `code_transpiler.py` (see `converter/docs/design/inline-over-runtime-wrappers.md`). The earlier 4.4 task ("port check_method_completeness() into dest's 7477 LOC luau_validator") no longer matches any code in the dest repo. §4.4 is now a diagnostic/reporting task.

### Current State

| | Source (code_validator) | Dest (post-2026-04-18) |
|---|---|---|
| Syntax validation | Regex-based report-only validator | `luau-analyze` CLI invoked in `code_transpiler.py:1508`; AI reprompt loop up to 2 retries (`code_transpiler.py:1584`) |
| C# residue cleanup | Regex rules | AI prompt + reprompt loop |
| Method completeness audit | `check_method_completeness()` — compares C# method names against Luau function definitions, honors `-- UNCONVERTED` / `-- TODO` markers | **Not present** |
| Approach | Report-only (ValidationResult) | AI reprompt until `luau-analyze` passes; no regex-based fixup layer |

### Assessment

The dest's `luau-analyze` gate catches syntax errors at transpile time, so the structural fix functions from the deleted regex validator are no longer the right integration surface. What **does** remain useful from source is the diagnostic layer: given a successfully-transpiled script, have all of the C# methods been either translated to Luau functions or explicitly marked `UNCONVERTED`? That's a **coverage audit**, not a syntax check, and it belongs next to the existing report generator.

### Steps

#### 4.4.1 Port `check_method_completeness()` as a diagnostic

Port the function from source's `code_validator.py` into a new module (e.g., `converter/converter/transpile_audit.py`) or directly into `report_generator.py`. It must:

1. Extract the set of C# method names from each source `.cs` file (signature-level, skip `// UNCONVERTED` / `// TODO` / commented-out bodies).
2. Extract the set of Luau function definitions (including local functions and methods on tables) from the transpiled `.luau` output.
3. Honor `-- UNCONVERTED` / `-- TODO` comments as intentional coverage markers.
4. Return a per-script list of missing method names — surfaced as **warnings**, not fixes.

Port source's `_strip_comments_and_strings()` helper at the same time so commented-out C# methods don't produce false positives.

#### 4.4.2 Wire diagnostics into `report_generator` + `luau-analyze` gate extension

1. Call the audit after the transpiler returns, before `write_output` assembles `rbx_place.scripts`. Append per-script missing-method warnings to `TranspiledScript.warnings` and surface them in the final JSON report via `report_generator.augment_report`.
2. Extend the existing `luau-analyze` invocation in `code_transpiler.py` to also cover Luau scripts generated by 4.2 (if any remain after the companion-script drop) and 4.5 (generated animation data scripts that contain executable code). Pure data-table modules are exempt — add a unit test that asserts the relevant generated scripts contain no executable constructs, so the exemption stays honest.

#### 4.4.3 Pair the audit with a prompt addition (required, not optional)

The dest's transpiler prompt currently tells the AI *"Convert the ENTIRE script faithfully. Do not skip methods"* (`code_transpiler.py:1165`) and *"Do NOT stub or skip complex methods"* (`code_transpiler.py:1169`). But there's no convention for **intentional** skips (unsafe reflection, editor-only APIs, `#if UNITY_EDITOR` blocks). Without that convention, the audit will flag every deliberate skip as a silent drop.

**Action:** Extend the system prompt with a single rule:

> "If you cannot faithfully translate a C# method (reflection, unsafe code, editor-only APIs, features with no Roblox equivalent), emit it as a stub Luau function with `-- UNCONVERTED: {short reason}` as the body. Do NOT silently drop methods — the transpile audit will flag drops as regressions."

The audit then honors `-- UNCONVERTED` / `-- TODO` markers as intentional coverage markers and only flags methods that are **missing entirely** — the genuine silent-drop failure mode.

Do NOT port source's structured error-code model (E001–E030 / W001–W031). It's speculative — no CI check or downstream consumer parses those codes today. Keep diagnostics as warning strings on `TranspiledScript.warnings`.

### Acceptance Criteria

- [ ] `check_method_completeness()` exists as a diagnostic in the dest (not a fix function)
- [ ] Missing-method warnings appear in the transpiler's `TranspiledScript.warnings` and in the final JSON report, with format `"Method '{name}' missing from transpile output (not stubbed, not marked UNCONVERTED)"`
- [ ] Comment/string stripping honors commented-out C# (no false positives)
- [ ] **Transpiler system prompt updated** with the UNCONVERTED-stub convention (4.4.3). A test-transpile of a representative script containing editor-only or reflection code produces stubs with `-- UNCONVERTED:` markers, not silent drops.
- [ ] Generated Luau scripts from 4.2/4.5 that contain executable code pass the `luau-analyze` gate before `write_output` finalizes (Cross-Cutting Constraint #1)
- [ ] A unit test asserts that 4.5 "controller data" modules are data-only (no executable constructs) — documents the exemption
- [ ] **Dual integration:** the audit runs both in the standalone `validate` CLI command (`convert_interactive.py`) AND during `write_output`'s finalization, so preserved-script rehydration paths see the same diagnostics
- [ ] **No structured error-code model introduced.** Diagnostics are warning strings; source's E001–E030 codes are not ported (no downstream consumer).

### Dependencies

- 4.2 and 4.5 must land first (the audit needs generated scripts to validate). Concretely: sequence 4.4 after 4.2 and 4.5, not before.
- 4.3 prompt engineering (§4.3.3) should land the UNCONVERTED-stub rule as part of its prompt pass, so 4.4 has a signal to honor. If 4.3 lands before 4.4, include the stub rule in 4.3's prompt changes; otherwise 4.4 adds it.
- No dependency on a resurrected `luau_validator.py` — **do not recreate that module.** The regression-style protection is implicit in `test_no_rejected_bridges.py`'s spirit: don't reintroduce deleted architecture.

---

## 4.5 animation_converter — Extend `animator_runtime` Data Path (High Complexity)

> **Scope rewritten 2026-04-24.** The earlier "dual-backend (TweenService vs config-table + AnimatorBridge.luau runtime)" framing is invalidated by Phase 3: `animator_bridge.luau` was **deleted** and its unique features (blend trees, `Play()`, `GetFloat`/`GetBool`/`GetInt`, Any-state transitions, lazy track loading, `Destroy()`) were **merged into `animator_runtime.luau`** — verified by `converter/tests/test_no_rejected_bridges.py::test_animator_runtime_has_consolidated_features`. `TransformAnimator.luau` was also deleted (its CFrame/Size curve animation is handled inline by generated TweenService scripts). The regression test forbids those two files from reappearing. §4.5 is now "extend the one remaining animator runtime (`animator_runtime.luau`) with blend-tree and controller-richness data; keep inline TweenService for simple and transform-only clips; do not introduce new runtime wrapper files."

### Current State

| | Source | Dest (2026-04-24) |
|---|---|---|
| LOC | 1,236 | 1,342 |
| Runtime approach | Config-table driven (`AnimatorBridge.lua` — deleted in dest) | Single runtime: `animator_runtime.luau` (consolidated); inline TweenService for simple + transform-only clips |
| Blend tree support | Yes (1D) | Partial — classID 206 detected in controller parse, but no config-table output yet |
| Root motion | Yes (`extract_fbx_root_motion`, unwired helpers) | No |
| Bone mapping | `UNITY_TO_R15_BONE_MAP` (humanoid — rejection filter only) | Not present |
| State machine | Config tables consumed by runtime | `animator_runtime.luau` interprets controller/keyframe data modules; TweenService inline for simpler cases |
| Output format | ModuleScript config tables + runtime bridge | Controller + clip data modules consumed by `animator_runtime.luau`; TweenService scripts inline |
| Controller parsing | `.controller` YAML → `AnimatorControllerData` | `.controller` YAML → `AnimatorController` |
| Clip parsing | `.anim` YAML → `AnimationClipInfo` | `.anim` YAML → `AnimClip` |
| JSON export | No | Yes (`export_controller_json`, `export_clip_keyframes`) |
| `_inject_runtime_modules` | — | Injects `animator_runtime.luau` only (pipeline.py ~L2081) |

### Assessment

The dest already runs a **single-runtime + inline-TweenService** model. The right Phase 4 work is not "add a second backend" but "make the existing `animator_runtime`-fed data richer," alongside keeping inline TweenService for clips that don't need the runtime at all.

- **Simple clip / transform-only clip** → inline TweenService (unchanged, dest already handles this).
- **Controller with blend trees, >3 Float/Int parameters, or complex state machine** → emit a richer controller data module that `animator_runtime.luau` interprets. No new runtime file; `animator_runtime.luau` already has the blend-tree, `Play()`, Any-state, and lazy-track-loading features consolidated from the deleted bridge.

**Key corrections from code audit:**
- Root motion is **unintegrated helper code** in source — `extract_fbx_root_motion()` and `generate_root_motion_config()` exist but are never called by `convert_animations()` or `convert_transform_animations()`. They depend on `assimp` and `Hips`-named FBX channels. **Treat as new-feature spike, not a port.**
- Blend tree resolution uses `m_Motion` file references to separate YAML docs with `m_Childs` / `m_BlendType`, NOT `m_BlendTree` as a direct field.
- `UNITY_TO_R15_BONE_MAP` is only used to **reject** humanoid clips from transform-only conversion, not to remap keyframes to R15 parts.
- Only the **base animator layer** is parsed; additional layers are ignored.
- Clips are resolved by **filename search**, not GUID lookup.

### Steps

#### 4.5.0 Transform-Only Animation Pipeline (Inline TweenService, No `TransformAnimator.luau`)

The plan's original analysis missed this entirely. Source has a complete separate pipeline for non-Animator animations:
- `is_transform_only_anim()` — detects clips that only animate position/rotation/scale (no bones)
- `convert_transform_animations()` — scans scenes, prefabs, and standalone `.anim` files for transform-only clips
- `generate_transform_anim_config()` — generated Luau config tables for the (now-deleted) `TransformAnimator.luau` runtime

**Action:** Port the detection + scanning logic (`is_transform_only_anim`, `convert_transform_animations`). Emit **inline TweenService scripts** for each detected clip — not config tables requiring a runtime wrapper. `TransformAnimator.luau` was deleted under the inline-over-runtime-wrappers policy; its curve-based CFrame/Size animation work is handled by generated TweenService scripts in the dest today. Follow that pattern.

**Note (per eng review):** `convert_transform_animations()` scans both scene nodes and prefab nodes (source line 921–932). Verify that the dest's prefab parser node/component interface is compatible with the ported scanning logic. If prefab nodes have a different structure, the prefab scan will silently produce zero results.

#### 4.5.1 Port Root Motion Extraction (⚠ NEW FEATURE, not a port)

Root motion helpers exist in source but are **never called** by any pipeline entry point. They are aspirational, unproven code. **Per eng review (Codex challenge):** This is new feature development, not a port of proven functionality. The code calls `assimp export` CLI (not pyassimp), assumes root bone is named `Hips` (only true for Humanoid rigs), and `generate_root_motion_config()` was never validated against a real Roblox runtime. Treat this accordingly.

**Action:**
1. Port `FbxRootMotion` dataclass and `extract_fbx_root_motion()` to dest as **dormant helpers** (matching source behavior).
2. **Wiring is a stretch goal**, not a blocking requirement. If time permits, add root motion extraction to the animation pipeline when `apply_root_motion` is true. This requires a spike: test with a real FBX file in Roblox Studio to verify the output format works.
3. Generate a root motion application script (source's `generate_root_motion_config()` adapted to dest's output style).
4. Note: requires `assimp` (optional dependency) and assumes root bone is named `Hips`.

#### 4.5.2 Port Blend Tree Support (Data for `animator_runtime.luau`)

Blend trees require the runtime-data approach because TweenService can't interpolate between multiple animations based on a parameter. The dest's `animator_runtime.luau` already has blend-tree support (per `test_no_rejected_bridges.py:94-99`: the runtime exposes `_startBlendTree`, `_updateBlendTree`, `_lazyLoadTrack`). What's missing is the **data-side** work: parsing blend trees out of the controller YAML and emitting them in the controller data module that `animator_runtime.luau` consumes.

**Action:**
1. Port `BlendTree` and `BlendTreeEntry` dataclasses to dest (extending `AnimatorController` / `AnimState`).
2. Add blend tree parsing to dest's `parse_controller_file()` — resolve via `m_Motion` file references to separate YAML documents containing `m_Childs` / `m_BlendType` (NOT a direct `m_BlendTree` field on the state).
3. Emit blend-tree data in the existing controller data module format consumed by `animator_runtime.luau`. Do NOT add a new runtime file — `animator_runtime.luau` is the single runtime.
4. Note: only 1D blend trees are supported; 2D blend trees are out of scope.

#### 4.5.3 Port R15 Bone Mapping

Source's `UNITY_TO_R15_BONE_MAP` maps Unity Humanoid bone names to Roblox R15 parts. However, in source it is only used as a **rejection filter** — clips targeting humanoid bones are excluded from transform-only conversion. It is NOT used to remap keyframes to R15 parts.

**Action:** Port the bone mapping dict to dest. Current use: rejection filter for transform-only pipeline. Future use: could enable actual humanoid keyframe remapping (new capability neither repo has).

#### 4.5.4 Implement Output Mode Selection

**Action:** Add an output-mode selection heuristic. Decision tree (refined per CEO review; re-homed to single-runtime model 2026-04-24):

```
FOR each Animator component:
  controller = parse_controller_file(...)

  IF controller parsing fails (binary format, corrupt YAML):
      → Log warning, skip this Animator entirely
      → Record in UNCONVERTED.md

  IF controller has ANY blend trees (even one state with BlendTree):
      → "runtime-data" mode (emit controller data module for animator_runtime.luau)
      → Reason: TweenService cannot interpolate between multiple animations by parameter;
                animator_runtime.luau already handles blend trees (_startBlendTree, _updateBlendTree)

  ELSE IF controller has >3 parameters WITH Float or Int types:
      → "runtime-data" mode
      → Reason: parameter-driven transitions are state-machine-heavy; animator_runtime handles them natively

  ELSE IF controller has root motion enabled (m_ApplyRootMotion = true):
      → "runtime-data" mode (or skip if 4.5.1 root-motion spike hasn't landed)
      → Reason: root motion requires frame-by-frame position/rotation extraction via animator_runtime

  ELSE:
      → "inline-tween" mode (generate self-contained TweenService script)
      → Self-contained; animator_runtime.luau is not required for this clip
```

**Both modes share the same single runtime: `animator_runtime.luau`.** The distinction is whether a given Animator requires it (runtime-data mode) or is simple enough to stand alone with inline TweenService. There is no "second runtime file" — `animator_bridge.luau` and `TransformAnimator.luau` were deleted and are guarded against by `test_no_rejected_bridges.py`.

**Logging (per CEO review):** Log the output-mode decision for each Animator to the conversion report: `"Animator '{name}': selected {mode} mode (reason: {reason})"`. This is critical for debugging "why does this animation look wrong."

Implementation:
1. Add a `mode: Literal["inline_tween", "runtime_data"]` field and `mode_reason: str` to the animation conversion result.
2. In `convert_animations()`, analyze each controller's complexity before choosing mode.
3. Runtime-data mode: extend the existing controller/clip data exporter (the one `animator_runtime.luau` already consumes) with blend-tree and richer parameter data from 4.5.2.
4. Inline-tween mode: use dest's existing `generate_tween_script()` / `generate_state_machine_script()` unchanged.
5. **Scene-scoped naming (per CEO review):** Generated animation module names must be prefixed with the scene name to avoid collisions across scenes/prefabs. E.g., `Level1_PlayerAnimConfig.luau`, not `PlayerAnimConfig.luau`. This prevents silent overwrites when multiple scenes have GameObjects with the same name. **Data flow (per eng review):** `convert_animations()` currently iterates all nodes across all scenes in a flat loop with no scene-name awareness. Implementation must either process scenes one at a time (passing scene name as a parameter) or add a `scene_name: str` field to the node data structure so it survives flattening. Same applies to `convert_transform_animations()`.
6. **Mode persistence (per eng review, re-scoped):** The selected `mode` (`"inline_tween"` or `"runtime_data"`) and `mode_reason` for each Animator must be persisted to `conversion_context.json` (under an `animation_modes` key). The preserved-script rehydration path reads this to decide whether to request `animator_runtime.luau` injection for that Animator's scripts. Without persistence, re-running the assemble phase after script edits would lose the mode decision and potentially fail to inject `animator_runtime.luau` when needed. There is **no bridge-selection toggle** anymore — only an injection-needed flag.

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

#### 4.5.6 Validate Both Modes

Test matrix:
| Scenario | Expected Mode | Key Validation |
|---|---|---|
| Simple position tween (1 clip, no controller) | inline_tween | Keyframes play correctly |
| Transform-only .anim (door/platform) | inline_tween (via 4.5.0 TweenService emitter) | Generated TweenService script drives movement; no runtime file required |
| State machine (3 states, Bool transitions) | inline_tween | State transitions fire on parameter change |
| Blend tree (1D, walk/run blend) | runtime_data | `animator_runtime.luau`'s `_startBlendTree` interpolates based on parameter |
| Root motion (character locomotion) | runtime_data | Character moves with animation (only if 4.5.1 spike lands) |
| Complex controller (>5 params, blend trees + transitions) | runtime_data | `animator_runtime.luau` runs the full state machine |

### Acceptance Criteria

- [ ] Transform-only pipeline ported and emits inline TweenService scripts (no `TransformAnimator.luau` reintroduced)
- [ ] Blend tree parsing added to controller parser (via `m_Motion` refs, not `m_BlendTree`)
- [ ] Blend tree data surfaces in the existing controller data module format consumed by `animator_runtime.luau` (no new runtime file)
- [ ] R15 bone mapping available (currently: rejection filter; future: keyframe remapping)
- [ ] Output-mode heuristic implemented with precise decision tree (blend trees → runtime_data; >3 Float/Int params → runtime_data; root motion → runtime_data; else → inline_tween)
- [ ] Output-mode decision logged per-Animator in conversion report with reason string
- [ ] Inline-tween mode (dest's existing) still works for simple animations
- [ ] Runtime-data mode feeds `animator_runtime.luau` correctly for complex controllers
- [ ] Both modes produce valid Luau that runs in Roblox Studio
- [ ] **Scene-scoped naming:** Generated animation module names prefixed with scene name (e.g., `Level1_PlayerAnimConfig.luau`) to prevent collisions across scenes/prefabs
- [ ] **Binary .controller graceful failure:** If controller YAML parsing fails (binary format, corrupt file), skip with warning and UNCONVERTED.md entry — never crash
- [ ] **Clip resolution graceful failure:** If .anim file not found by filename search, skip that clip with warning — never crash
- [ ] **Corrupt .anim resilience (per eng review):** Malformed keyframe data (wrong type, missing fields, NaN values) → skip that curve, log warning, continue with remaining curves. Never crash on bad animation data.
- [ ] **assimp CLI failure resilience (per eng review):** If root motion extraction fails (assimp not installed, CLI timeout, missing FBX), skip root motion for that animator with warning — do not block the entire animation pipeline.
- [ ] **Transform-only prefab scanning (per eng review):** Transform-only animation detection works for both scene nodes AND prefab nodes.
- [ ] Existing dest animation tests still pass, including `test_no_rejected_bridges.py::test_animator_runtime_has_consolidated_features` (the consolidated feature set must remain intact)
- [ ] **`_inject_runtime_modules()` injection trigger:** When any Animator in the output selects `runtime_data` mode, `animator_runtime.luau` is auto-injected (it already is today — verify the trigger is reachable for the new mode flag). Do NOT reintroduce `animator_bridge.luau` or `TransformAnimator.luau` injection — those files are deleted and the regression test forbids their return.
- [ ] **Generated animation data modules persist to disk** in a known subdirectory that `write_output` rehydration handles (current rewrite handles `scripts/` and `scripts/animations/` — verify the subdir used for controller data modules is covered, or extend the rewrite).

### Dependencies

- `animator_runtime.luau` (already in dest) is the single consumer for runtime-data mode. `AnimatorBridge.luau` and `TransformAnimator.luau` were deleted and must NOT be reintroduced (guarded by `test_no_rejected_bridges.py`).
- Phase 3 item 11 (extend `write_output` disk rewrite) should be completed or extended to cover the controller-data module subdirectory.
- 4.7 (scene_parser controller GUID extraction) is a **hard prerequisite** — `animator_runtime` needs to know which controllers to parse.
- 4.4 runs **after** 4.5 (the method-completeness audit and `luau-analyze` gate must cover any executable Luau generated by 4.5).

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
3. **Decision (CEO review):** Use `unity-fps-output/` as the reference project — its UI elements have known positions. Convert with source's transform, open in Studio, verify UI element positions match the original Unity layout. If flipped, use dest's transform instead.
4. Document the decision with before/after evidence

### Acceptance Criteria

- [ ] Font mapping resolves Unity fonts to Roblox `Enum.Font`
- [ ] TextAnchor → TextXAlignment + TextYAlignment mapping complete
- [ ] Sprite-vs-solid-color distinction for Images
- [ ] Partial anchor warning emitted
- [ ] **RectTransform resilience (per eng review):** Malformed RectTransform properties (missing anchors, invalid pivot values, NaN positions) → skip that element with warning, record in UNCONVERTED.md. Never crash on bad UI data.
- [ ] **Canvas-less UI nodes (per eng review):** UI elements without a parent Canvas → skip with warning, not crash
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

The sub-items have few hard dependencies between them. Recommended order optimizes for risk reduction (hardest first) and dependency satisfaction. Updated 2026-04-24 per Phase 3 reconciliation.

```
┌─────────────────────────────────────────────────────────┐
│ Pass 0 — Plan rewrite (applied 2026-04-24):             │
│   Remove deleted/superseded assumptions, correct        │
│   baselines, rename §4.4/§4.5 to match current arch.    │
│   See "Phase 3 Reconciliation Log" at end of file.      │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ Can start immediately (no dependencies):                │
│   4.1 api_mappings        (Low, ~1hr)                   │
│   4.3 code_transpiler     (Medium, ~3hr)                │
│        └─ luau-analyze gate already in place            │
│   4.6 ui_translator       (Medium, ~2hr)  [⚠ Y-invert] │
│   4.7 scene_parser        (Low, ~1hr)                   │
│        └─ adds referenced_animator_controller_guids     │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ Start after 4.7 (hard dependency):                      │
│   4.5 animation_converter (High, ~5hr)                  │
│        └─ HARD DEP: scene_parser controller GUIDs (4.7) │
│        └─ single runtime target: animator_runtime.luau  │
│           (AnimatorBridge.luau and TransformAnimator     │
│            .luau were deleted — do NOT reintroduce)     │
│        └─ includes transform-only pipeline (4.5.0) as    │
│           inline TweenService, not a runtime wrapper    │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ Start after 4.5 + Phase 3 rehydration:                  │
│   4.2 material_mapper     (High, ~4.5hr)                │
│        └─ static material work + 4.2.5a schema add      │
│        └─ companion-scripts clause DROPPED              │
│        └─ 4.2.5b (baker wiring) deferred post-Phase 4   │
│   4.4 transpile diagnostics (Low, ~1hr)                 │
│        └─ method-completeness audit feeds               │
│           report_generator                              │
│        └─ extends luau-analyze gate to cover executable │
│           Luau generated by 4.2/4.5                     │
└─────────────────────────────────────────────────────────┘
```

**Ordering rationale (CEO + Codex review; reconciled 2026-04-24):**
- 4.7 → 4.5 is a **hard dependency**: animation_converter consumes `referenced_animator_controller_guids` from scene_parser.
- 4.4 moved late (post-4.2 and post-4.5): the method-completeness audit and `luau-analyze` gate must cover any executable Luau generated by those modules. Cross-cutting constraint #1 is now scoped to executable Luau only — pure data-table modules are exempt.
- Phase 3 rehydration/persistence (conversion_plan.json) is a **prerequisite** for Phase 4 modules that generate scripts.
- 4.5 no longer depends on `AnimatorBridge.luau` / `TransformAnimator.luau` — those were deleted and the single target is `animator_runtime.luau`.

---

## Testing Strategy

Each reconciliation item should have:

1. **Existing dest tests pass** — run before and after. Zero regressions.
2. **Ported source test cases** — for capabilities that came from source, port the relevant test assertions (not the test scaffolding — adapt to dest's test structure).
3. **Integration smoke test** — after all 7 items complete, run a full pipeline conversion on a test Unity project to verify modules compose correctly.
4. **Cross-module integration tests (per eng review):** Automated tests for critical module boundaries:
   - `scene_parser` → `animation_converter`: controller GUID extraction feeds animator discovery
   - `material_mapper` → `rbxlx_writer`: MaterialMapping consumption produces valid RBXLX
   - `code_transpiler` → `code_validator`: transpiled Luau passes validation without regressions
   - End-to-end: parse scene → transpile scripts → validate → assemble output (minimal, no upload)
5. **Rehydration path test (per eng review):** At least one test that exercises the preserved-script assemble flow: transpile → edit scripts on disk → re-assemble → verify edits survive and correct runtime modules are injected.

---

## Risk Mitigations

| Risk | Mitigation |
|---|---|
| Material mapper port breaks `scene_converter` / `rbxlx_writer` integration | Add `MaterialMapping` field changes behind optional fields with defaults. Run integration test before merging. |
| Unknown shaders silently produce no `roblox_def` | Source does NOT fall back to Standard extraction for unknown shaders. Decide explicitly: add a fallback in dest, or preserve strict behavior and log a warning. |
| Accidental reintroduction of deleted bridges | `converter/tests/test_no_rejected_bridges.py` is CI-enforced and will fail any PR that restores `animator_bridge.luau`, `TransformAnimator.luau`, `bridge_injector.py`, `mesh_splitter.py`, or the other seven rejected wrappers. Don't disable it. |
| §4.5 output-mode selection adds maintenance burden | Mode selection is deterministic (based on controller complexity). Document the heuristic clearly. Inline-tween and runtime-data both target the same single runtime (`animator_runtime.luau`); there is no parallel backend to sunset. |
| Root motion code is unintegrated in source | Port as dormant helpers. Wiring is a stretch goal requiring a real FBX validation spike. Do not treat as equivalent to porting proven code. |
| Only base animator layer parsed | Multi-layer support is out of scope. Document this limitation. May cause missing animations for controllers with override/additive layers. |
| UI Y-inversion contradiction | Source code inverts Y but header comment says no inversion needed. Must test with real Unity Canvas before porting math. Wrong choice flips all layouts vertically. |
| Dependency-ordered transpilation slows down concurrent execution | Batch by dependency level preserves concurrency within levels. Measure wall-clock time before/after. |
| `scene_parser` classID coverage split across two files | Must diff both `scene_parser.py` AND `unity_yaml_utils.py` against dest — checking only the parser misses delegated component coverage. |
| Union merge of api_mappings introduces conflicting entries | Keep dest's value when both repos map the same key differently. Log conflicts for manual review. |
| Non-deterministic dependency cycle breaking (eng review) | Source's DFS cycle break depends on dict ordering. Fix: alphabetical sort before DFS. |
| Integration regression across 4.x items (eng review) | Each 4.x item is a separate PR with CI. Integration checkpoints after 4.2 and 4.5. Tag rollback point before Phase 4. |
| Custom shader patterns are game-specific (eng review) | Port the regex-table mechanism only. Make the table configurable per-project. Do NOT port the Trash Dash companion-script pattern — that contradicts the inline-over-runtime-wrappers policy. |
| 4.2.5a schema add without 4.2.5b baker wiring appears as dead field | Acceptable — the field is cheap, unblocks future wiring, and matches the deferred Phase 3 item 2. Track 4.2.5b in `TODO.md` for when a test project with vertex-color-only materials is available. |
| Orchestration/glue code changes underestimated (eng review) | +500/+400 LOC estimates don't include changes to pipeline.py, scene_converter.py, rbxlx_writer.py, write_output. Budget an additional ~200 LOC for integration wiring. |

---

## Eng Review Log (2026-04-12)

**Reviewer:** Claude Opus 4.6 + Codex (outside voice)  
**Branch:** refactor/skill-to-code  
**Scope mode:** HOLD SCOPE  

### Section 1: Architecture Review
- 1 issue found: Animation backend choice must persist to ConversionContext for rehydration path. **Applied.**
- Asset ID placeholder format inconsistency noted, non-blocking.

### Section 2: Code Quality Review
- `_convert_material()` (385 lines) and `_process_textures()` (370 lines) are monolithic. Natural decomposition happens during port — not a separate task.
- Broad `Exception` catch in texture processing should not carry forward. Plan already addresses via resilience criterion.
- Result dataclass naming inconsistency (anims vs animators) — minor, fix during port.
- All 4 modules have complete type annotations, no `Any`, no mutable defaults. Clean.

### Section 3: Test Review
- 440 unit tests across 9 files. Strong unit coverage, zero integration coverage.
- **Added to plan:** Cross-module integration tests (4 specific module boundaries) and rehydration path test.

### Section 4: Performance Review
- Repeated `Image.open()` calls in texture processing. **Added** guidance to port ops accepting PIL.Image instances.
- `pre_tile` memory bomb (4K × 4× = 1GB). **Added** clamp-before-allocate requirement.
- No other performance concerns.

### Outside Voice (Codex): 15 findings, 7 applied
Applied to plan:
1. Cross-cutting constraints now have explicit **owners** (4.4 owns validation ordering, 4.2 owns asset ID contract)
2. Scene-scoped naming data flow path specified (scene_name parameter or field)
3. Root motion reclassified as new feature / stretch goal (not a port)
4. Custom shader patterns: port mechanism, not game-specific patterns
5. Dependency cycle-breaking: deterministic alphabetical sort required
6. Error resilience parity: 4.5 and 4.6 now have same-level resilience criteria as 4.2
7. `referenced_guids` filtering acceptance criterion added
8. Rollback strategy: separate PRs, CI gates, integration checkpoints

Acknowledged but not requiring plan changes:
- Dual-backend long-term maintenance (already in risk table with sunset clause)
- Y-inversion tolerance (concrete test protocol recommended, added to 4.6.7)
- `check_method_completeness` contract (diagnostic-only, low impact)
- Effort estimates for orchestration glue (added to risk table)

### Status: DONE (at eng review time)

Plan is ready for implementation. Total changes: 19 plan updates across CEO review (11) + eng review (8). All cross-cutting constraints have owners. All acceptance criteria are verifiable. Execution order is sound with integration checkpoints.

---

## Phase 3 Reconciliation Log (2026-04-24)

**Reviewer:** Claude Opus 4.7 + Codex (outside voice, session `019dbcb0-cf86-7460-816f-88755d89263a`)
**Dest repo:** `unity2rbxlx/` @ main (commit `385c669`)
**Trigger:** Phase 1-3 landed with re-scoping that invalidated several Phase 4 assumptions.

### Load-bearing invalidations (sourced from dest repo)

1. **`converter/converter/luau_validator.py` was DELETED** on 2026-04-18 (commit `594238c`). The 8,633-LOC regex validator was replaced by a `luau-analyze` + AI reprompt loop in `code_transpiler.py:1508`. See `converter/docs/design/inline-over-runtime-wrappers.md`.
2. **Nine runtime bridges + `bridge_injector.py` were REJECTED** under the inline-over-runtime-wrappers policy (adopted 2026-04-14). The rejected set: `Input.luau`, `Time.luau`, `Coroutine.luau`, `physics_queries.luau`, `GameObjectUtil.luau`, `MonoBehaviour.luau`, `StateMachine.luau`, `animator_bridge.luau`, `TransformAnimator.luau`, and the Python `bridge_injector.py` + `mesh_splitter.py` modules. A CI-enforced regression test (`converter/tests/test_no_rejected_bridges.py`) prevents reappearance.
3. **`animator_bridge.luau`'s unique features were MERGED into `animator_runtime.luau`.** Blend trees (`_startBlendTree`, `_updateBlendTree`), `Play()`, `GetFloat`/`GetBool`/`GetInt`, Any-state transitions, lazy track loading, and `Destroy()` now live in the single consolidated runtime. Verified by `test_no_rejected_bridges.py::test_animator_runtime_has_consolidated_features`.
4. **`mesh_splitter.py` was rejected**, superseded by scene_converter's sub-mesh hierarchy path.
5. **`vertex_color_baker.py` is NOT wired** into the pipeline (Phase 3 augmented plan item 2: deferred pending a test project with vertex-color-only materials).
6. **`generate_bootstrap_script`, `extract_serialized_field_refs`, `generate_prefab_packages`** are superseded or deferred (Phase 3 augmented plan items 8/9/10).

### Baseline corrections applied

| Module | Plan baseline (stale) | Actual (2026-04-24) |
|---|---|---|
| `luau_validator.py` | 7,477 LOC, 22 fix functions | **Deleted** |
| `code_transpiler.py` | 2,083 LOC | 1,658 LOC |
| `material_mapper.py` | 727 LOC, 6 shaders | 783 LOC, 10 entries in `_SUPPORTED_SHADERS` |
| `MaterialMapping.uses_vertex_colors` | — | Field missing (4.2.5a adds it) |
| `ParsedScene.referenced_animator_controller_guids` | — | Field missing (4.7 adds it) |
| `referenced_guids` filtering in `map_materials()` | To be ported | **Already landed** in Phase 3 |

### Plan changes applied

- **Cross-Cutting Constraint #1 (validation ordering)** rewritten: scoped to executable Luau only; routed through `luau-analyze` gate instead of the deleted `luau_validator`.
- **Cross-Cutting Constraint #6 (new)** added: inline-over-runtime-wrappers policy with regression-test reference.
- **§4.2.4** companion-script clause dropped; replaced with static-extraction guidance consistent with the inline policy.
- **§4.2.5** split into 4.2.5a (schema add — land in Phase 4) and 4.2.5b (baker wiring — deferred post-Phase 4).
- **§4.2 acceptance criteria** updated: `referenced_guids` filtering reframed as "preserve existing behavior"; added "no new per-material runtime wrapper scripts" requirement.
- **§4.3.3** prompt-engineering guidance updated: do NOT port source's bridge-module import patterns; steer AI toward inline translations via `api_mappings` / `UTILITY_FUNCTIONS`.
- **§4.4** rewritten: no longer a validator port. Now a method-completeness diagnostic feeding `report_generator`, plus an extension of the existing `luau-analyze` gate to cover executable Luau generated by 4.2/4.5.
- **§4.5** rewritten: single-runtime model (`animator_runtime.luau` only). "Config-table vs TweenService" reframed as "runtime-data mode vs inline-tween mode," both targeting the same runtime. `AnimatorBridge.luau` / `TransformAnimator.luau` injection requirements removed. Backend-choice persistence simplified to an injection-needed flag.
- **§4.5.0** transform-only pipeline now emits inline TweenService scripts (not config tables for the deleted `TransformAnimator.luau`).
- **§4.5.2** blend-tree port now emits data for the existing `animator_runtime.luau` (no new runtime file).
- **Execution Order** diagram updated to reflect new 4.4 (post-4.2/4.5) and drop the rejected-bridge dependency chain.
- **Risk Mitigations** table: removed "dual-backend maintenance" risk; added "accidental reintroduction of deleted bridges" (mitigated by regression test); added "4.2.5a field without 4.2.5b baker" risk (accepted).

### Ready for implementation

- **Tier 1 — ready now:** 4.1 api_mappings, 4.7 scene_parser, 4.6 ui_translator, 4.2.5a schema add.
- **Tier 2 — start after Tier 1 lands:** 4.3 code_transpiler, 4.5 animation_converter (hard-dep on 4.7).
- **Tier 3 — post 4.2/4.5:** 4.4 diagnostic + `luau-analyze` extension.
- **Deferred post-Phase 4:** 4.2.5b baker wiring, 4.5.1 root-motion spike.

### Decisions resolved 2026-04-24 (evidence-based)

**Q1: Keep §4.4 — paired with a transpiler prompt change.** Evidence from `converter/converter/code_transpiler.py:1165, 1169`: the dest's AI prompt already forbids method skips (*"Do not skip methods or simplify logic"*), but there is **no detection layer** — a clean `luau-analyze` pass with three missing methods ships today. The audit is the detection layer. It's worth ~60 LOC **if** it's paired with a prompt addition telling the AI to emit `-- UNCONVERTED: {reason}` stubs for intentional skips, so the audit has a signal to honor. See §4.4.3. Source's structured error-code model (E001–E030) is dropped — no downstream consumer.

**Q2: Formalize the existing fallback — dest code already does it informally.** Evidence from `converter/converter/material_mapper.py:222-229`: unknown shaders already run through the full extraction path with multiple fallback texture slot names. The CEO "add a Standard fallback" decision describes behavior that is already present; the Phase 4 work reduces to (a) extracting the fallback into a named `_apply_standard_fallback()` helper, (b) adding a `shader_category` enum/field on `MaterialMapping`, (c) emitting a formal UNCONVERTED.md entry (severity LOW) — **including** for `Shader Graphs/*` and `Custom/*` shaders, which currently suppress the warning entirely and therefore hide real coverage gaps. No CEO re-review needed; the 10-shader baseline doesn't change the decision because particle/sprite/UI/custom shaders still hit the fallback path today. See §4.2.1 step 3.
