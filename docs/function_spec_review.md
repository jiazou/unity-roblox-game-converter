# Function Specification Review — Gap Analysis

> Date: 2026-03-02
> Scope: Compare the "Function Specifications for Unity→Roblox Conversion Tool" against the current master plan and implementation
> Repository: unity-roblox-game-converter

---

## Summary

The function specification defines **37 functions** across 8 pipeline stages. Against the current codebase (~4,200 lines across 11 modules + orchestrator):

| Status | Count | Functions |
|--------|-------|-----------|
| Fully implemented | 10 | UnityAssetExporter, MeshSimplifier, MaterialMapper, LLMTranslatorWrapper, UnityProjectImporter, AssetUploader, BuildOrchestrator, JobScheduler, ReviewInterface, HITL_JobScheduler |
| Partially implemented | 6 | CSharpParser, APIMapper, AssetQualityAssurance, LoggingAndAudit, AuditTrail, FeedbackIngestion |
| Not implemented | 21 | TextureAtlasGenerator, AnimationRetargeter, AudioConverter, CodeValidator, CodeQA, TestGenerator, UIExtractor, LayoutTranslator, UIGenerator, UIQA, NetworkAnalyzer, RemoteEventGenerator, ServerAuthorityMapper, RojoIntegrator, PromptManager, BatchRequestHandler, CacheManager, CostEstimator, FineTuneManager, LLMMonitor, RetryBackoff |

**Coverage: 8/37 fully implemented (22%), 13/37 at least partially (35%), 24/37 missing (65%).**

The codebase is strongest in the asset pipeline (materials, meshes, scene parsing) and weakest in UI, networking, and LLM ops.

> **Update (2026-03-02):** The HITL gap (ReviewInterface, FeedbackIngestion, HITL_JobScheduler) is now largely addressed by the `/convert-unity` Claude Code skill, which provides an interactive conversion workflow with human decision points at each phase. See the [Human-in-the-Loop](#human-in-the-loop) section for details.

---

## Detailed Function-by-Function Analysis

### Asset Pipeline

#### 1. UnityAssetExporter (P0) — IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Module | — | `modules/asset_extractor.py` (117 lines) |
| Purpose | Extract 3D models/textures from Unity scenes | Walks `Assets/` directory, catalogues all assets by type |
| Inputs | Unity project file or scene identifier | `unity_project_path` |
| Outputs | Mesh files (FBX/GLTF), texture files (PNG) | `AssetManifest` with per-file entries (path, kind, size, SHA256) |

**Needed?** Yes — core discovery step for the pipeline.

**Assessment**: Implemented, but with a different approach than the spec envisions. The spec implies *exporting* from Unity binary scene data, while the implementation discovers raw asset files already present in the project's `Assets/` directory. This is actually the correct approach for Unity projects (assets are stored as files), so the spec's description is slightly misleading. **No gap.**

**In master plan?** Yes — listed in README module table as `asset_extractor`.

---

#### 2. MeshSimplifier (P0) — IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Module | — | `modules/mesh_decimator.py` (263 lines) |
| Purpose | Reduce mesh complexity for Roblox (≤10K tris) | Conservative decimation with quality floor |
| Inputs | Raw mesh (FBX) | List of mesh `Path` objects |
| Outputs | Simplified mesh variants (LODs) | `DecimationResult` with per-mesh entries |

**Needed?** Yes — Roblox MeshPart limit is 10,000 faces.

**Assessment**: Fully implemented. Uses trimesh for quadric decimation. Conservative approach: meshes under the limit are copied unchanged, quality floor of 60%, targets 8K faces (leaving headroom). Only difference from spec: does NOT generate multiple LOD variants — it produces a single decimated mesh. LOD generation is not needed because Roblox doesn't support mesh LODs on MeshPart.

**In master plan?** Yes — listed in README as `mesh_decimator`.

---

#### 3. TextureAtlasGenerator (P0) — NOT IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Pack multiple texture maps into atlases | N/A |
| Outputs | UV atlas image(s), UV remap data | N/A |

**Needed?** Questionable for POC. Roblox `SurfaceAppearance` supports one material per MeshPart, and each MeshPart has its own texture set. Atlas packing is an optimization that reduces draw calls but adds UV complexity. The current implementation handles textures per-material, which is simpler and correct.

**Recommendation**: **Defer to post-POC.** Atlas packing requires UV remapping on meshes too, which is non-trivial. Not needed for the acceptance criteria (≤30% manual correction, no crashes). Downgrade from P0 to P2 for POC scope.

**In master plan?** Not mentioned anywhere in the codebase docs.

---

#### 4. MaterialMapper (P1) — IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Module | — | `modules/material_mapper.py` (1,206 lines) |
| Purpose | Convert Unity materials to Roblox SurfaceAppearance | Full shader-aware material conversion |
| Inputs | Material definitions (albedo, metal, rough, normal) | `.mat` YAML files + GUID resolution |
| Outputs | Roblox material type + PBR parameters | `RobloxMaterialDef` with SurfaceAppearance fields |

**Needed?** Yes — core visual fidelity feature.

**Assessment**: This is the most thoroughly implemented module. Handles:
- Built-in Standard, Standard (Specular), Legacy, URP Lit/Unlit, HDRP, Particle, Sprite shaders
- Custom shader analysis (source parsing, `#include` resolution, property detection)
- Texture operations: copy, channel extraction, inversion, AO baking, pre-tiling, grayscale, threshold alpha
- UNCONVERTED.md report generation
- Companion Luau scripts for animated shaders (blinking, rotation)
- Both `.mat` YAML format versions (v2, v3)

Goes well beyond what the spec describes. **No gap.**

**In master plan?** Yes — the primary focus of `docs/material_converter_plan.md` (539 lines) and `docs/material_mapping_research.md` (862 lines).

---

#### 5. AnimationRetargeter (P1) — NOT IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Retarget Unity animations to Roblox rigs | N/A |
| Outputs | Roblox AnimationClip data | N/A |

**Needed?** Yes, for games with animated characters. But scope depends on the target game.

**Assessment**: The asset_extractor discovers `.anim` files but there's no conversion logic. Roblox uses a different animation system (KeyframeSequence/AnimationClip via AnimationEditor). Bone name mapping and IK/FK retargeting are complex. For the POC, animations could be listed in the conversion report as "requires manual recreation in Roblox AnimationEditor."

**Recommendation**: **Defer to post-POC.** Log discovered animations as unconverted in the report. Keep at P1 for the full product.

**In master plan?** Not mentioned in any document.

---

#### 6. AudioConverter (P2) — NOT IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Convert audio assets to Roblox-supported format | N/A |

**Needed?** Yes for completeness, but low effort and low risk.

**Assessment**: Roblox accepts OGG and MP3 directly. Unity projects typically store WAV/MP3. The conversion would be a thin ffmpeg wrapper. The asset_extractor already discovers `.wav`, `.mp3`, `.ogg` files.

**Recommendation**: **Keep at P2.** Simple to implement when needed. Can be a 20-line ffmpeg shell call.

**In master plan?** Not mentioned.

---

#### 7. AssetQualityAssurance (P1) — PARTIALLY IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Inspect imported assets for issues | Spread across modules |
| Outputs | QA report (warnings/errors) | UNCONVERTED.md + conversion_report.json |

**Needed?** Yes — quality gates catch conversion errors early.

**Assessment**: QA functionality is distributed rather than centralized:
- `material_mapper.py` generates UNCONVERTED.md with per-material QA (severity, workarounds)
- `mesh_decimator.py` reports warnings for skipped/problematic meshes
- `code_transpiler.py` flags low-confidence translations for review
- `report_generator.py` aggregates all warnings and errors

No dedicated "run this mesh through an LLM for normal issues" step exists, but the practical QA value is delivered through the existing warning/error system.

**Recommendation**: **Current coverage is adequate for POC.** A dedicated AssetQA module with LLM inspection could be added later but is not blocking.

**In master plan?** Partially — the UNCONVERTED.md system is specified in `docs/material_converter_plan.md`.

---

### Code Pipeline

#### 8. CSharpParser (P0) — PARTIALLY IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Module | — | Part of `modules/code_transpiler.py` (203 lines) |
| Purpose | Parse Unity C# scripts into AST or tokens | Regex-based pattern matching |
| Deps | Roslyn or Mono.CSharp parser | `tree-sitter`, `tree-sitter-c-sharp` in requirements.txt but **not used in code** |

**Needed?** Yes — accurate C# parsing is needed for reliable translation.

**Assessment**: The code_transpiler.py uses regex substitutions, NOT a proper AST parser. The requirements.txt lists `tree-sitter` and `tree-sitter-c-sharp` as dependencies, suggesting AST-based parsing was planned but never implemented. The regex approach handles simple patterns (variable declarations, Debug.Log, void methods, lifecycle hooks, `this.` references) but cannot handle:
- Nested class hierarchies
- Generic types
- LINQ expressions
- Complex control flow
- Inheritance and interfaces

The AI transpilation path (Claude) compensates for this limitation by sending raw C# text and receiving Luau output, bypassing the need for AST parsing entirely.

**Recommendation**: **Adequate for POC with AI path enabled.** For the rule-based path, proper tree-sitter AST parsing would significantly improve accuracy. The dependencies are already declared — just needs implementation.

**In master plan?** Listed in README as part of `code_transpiler`. Not detailed in any planning doc.

---

#### 9. APIMapper (P0) — PARTIALLY IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Map Unity APIs to Roblox equivalents | `_RULE_PATTERNS` list in code_transpiler.py |
| Outputs | Lookup table or direct replacement | 7 regex pattern replacements |

**Needed?** Yes — the bridge between C# Unity API and Luau Roblox API.

**Assessment**: Current implementation has only 7 regex rules:
1. Variable declarations → `local`
2. `Debug.Log` → `print`
3. `void` → `local function`
4. `Start()` → `AncestryChanged`
5. `Update()` → `Heartbeat:Connect`
6. `this.` → `self.`
7. Comment style preservation

Missing major mappings: `Physics.Raycast` → `workspace:Raycast`, `GetComponent<T>()` → `FindFirstChildOfClass`, `Instantiate` → `Clone`, `Destroy` → `Destroy`, `Mathf.*` → `math.*`, `Vector3.*` → `Vector3.new`, `Transform.*` → `CFrame`, `Coroutine` → task library, and hundreds more.

Again, the AI transpilation path (Claude) implicitly handles API mapping as part of its translation, making a comprehensive lookup table less critical when AI is enabled.

**Recommendation**: **Significant gap for rule-based mode.** If rule-based transpilation is meant to be the default/fallback, the API mapping table needs major expansion. Consider building a comprehensive JSON mapping file. **Adequate for POC if AI mode is the primary path.**

**In master plan?** Not detailed in any planning doc. Implicit in `code_transpiler`.

---

#### 10. LLMTranslatorWrapper (P0) — IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Module | — | `_ai_transpile()` in `modules/code_transpiler.py` |
| Purpose | Interface with Claude to translate code | Sends C# to Claude, receives Luau |
| Deps | Claude API credentials, prompt templates | Anthropic SDK, single hardcoded prompt |

**Needed?** Yes — core LLM integration for code translation.

**Assessment**: Fully implemented. Uses the Anthropic Python SDK. Sends a clear prompt: "Convert the following Unity C# MonoBehaviour script to idiomatic Roblox Luau." Handles markdown fence stripping from responses. Error handling wraps failures gracefully (preserves original C# as comments). Default confidence of 0.9 for AI results.

**Differences from spec:**
- Spec mentions ~500 tokens per call — actual usage will vary with script size
- Spec mentions batching multiple methods — current implementation sends one file per call
- Spec mentions "hundreds of calls" — current implementation does one call per .cs file

**In master plan?** Yes — listed as a strategy option in code_transpiler.

---

#### 11. CodeValidator (P1) — NOT IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Verify semantic validity of translated code | N/A |
| Deps | Roblox Runtime or mock environment | N/A |

**Needed?** Yes — without validation, translation correctness is unknown.

**Assessment**: No Luau code validation exists. The transpiler assigns confidence scores but doesn't actually verify the generated code compiles or runs correctly. A Roblox Luau linter/parser (like `luau-analyze` or `selene`) could provide static validation. Runtime validation would require a Roblox sandbox.

**Recommendation**: **Important gap.** At minimum, add Luau syntax validation (parse check). Consider integrating `luau` CLI for type checking. Runtime validation (test execution) is post-POC scope.

**In master plan?** Not mentioned.

---

#### 12. CodeQA (P2) — NOT IMPLEMENTED

**Needed?** Nice-to-have. The AI transpilation already produces reviewed code. An additional LLM review pass adds cost with diminishing returns for POC.

**Recommendation**: **Defer.** P2 is correct.

---

#### 13. TestGenerator (P2) — NOT IMPLEMENTED

**Needed?** Nice-to-have for comprehensive coverage. Not blocking POC.

**Recommendation**: **Defer.** P2 is correct.

---

### UI Pipeline

#### 14. UIExtractor (P1) — NOT IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Pull Unity UI definitions (positions, images) | N/A |
| Inputs | Unity scene Canvas data | N/A |

**Needed?** Yes, if the target game has Unity UI elements. Unity Canvas/UGUI data is stored in scene files and can be parsed.

**Assessment**: The `scene_parser.py` already parses `.unity` scene files and can access Canvas/UI components by classID (Canvas=223, CanvasRenderer=222, RectTransform=224, Image=114). The infrastructure to extract UI data exists but hasn't been specialized for UI elements.

**Recommendation**: **Needed for medium games. Keep at P1.** Can be built on top of the existing scene parser.

**In master plan?** Not mentioned.

---

#### 15. LayoutTranslator (P1) — NOT IMPLEMENTED

**Needed?** Yes, paired with UIExtractor. Unity anchored layout → Roblox UDim2 conversion is a well-defined mapping problem.

**Recommendation**: **Keep at P1.** Depends on UIExtractor.

---

#### 16. UIGenerator (P2) — NOT IMPLEMENTED

**Needed?** Nice-to-have. Could be an LLM-assisted step.

**Recommendation**: **Defer.** P2 is correct.

---

#### 17. UIQA (P2) — NOT IMPLEMENTED

**Needed?** Low priority for POC.

**Recommendation**: **Defer.** P2 is correct.

---

### Networking Adapter

#### 18. NetworkAnalyzer (P1) — NOT IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Identify Unity network calls (RPCs, sync) | N/A |

**Needed?** Yes, for multiplayer games. Unity's networking (Mirror, Photon, UNet, Netcode for GameObjects) uses attributes (`[Command]`, `[ClientRpc]`, `[SyncVar]`) that can be detected by scanning C# code.

**Assessment**: The code_transpiler.py regex patterns don't look for networking attributes. The AI transpilation path might detect them but won't generate Roblox RemoteEvent equivalents without specific context.

**Recommendation**: **Keep at P1 for multiplayer games.** For single-player POC targets, this can be deferred.

**In master plan?** Not mentioned.

---

#### 19. RemoteEventGenerator (P1) — NOT IMPLEMENTED

**Needed?** Only for multiplayer games. Depends on NetworkAnalyzer.

**Recommendation**: **Keep at P1, paired with NetworkAnalyzer.**

---

#### 20. ServerAuthorityMapper (P2) — NOT IMPLEMENTED

**Needed?** Architecture decision support. Lower priority.

**Recommendation**: **Defer.** P2 is correct.

---

### Tooling & CI

#### 21. UnityProjectImporter (P0) — IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Load Unity project files into tool pipeline | Distributed across 4 modules |
| Outputs | Structured asset/code dump | AssetManifest + GuidIndex + ParsedScene[] + PrefabLibrary |

**Assessment**: Fully implemented across multiple modules:
- `asset_extractor.py` — discovers and catalogues assets
- `guid_resolver.py` — builds GUID↔path index from `.meta` files (305 lines)
- `scene_parser.py` — parses `.unity` scene files (408 lines)
- `prefab_parser.py` — parses `.prefab` files (338 lines)

Together these modules provide a richer "project import" than what the spec describes. **No gap.**

**In master plan?** Yes — all four modules listed in README.

---

#### 22. RojoIntegrator (P0 in spec) — NOT IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Sync converted assets/code to Roblox Studio via Rojo | N/A |
| Deps | Rojo CLI | N/A |

**Needed?** Depends on workflow. The current tool writes `.rbxl` files directly, which can be opened in Roblox Studio. Rojo is an alternative workflow for file-system-based development.

**Assessment**: The current approach (direct `.rbxl` writing via `rbxl_writer.py` + optional Open Cloud upload via `roblox_uploader.py`) is actually more self-contained than requiring Rojo. Rojo requires separate installation and configuration.

**Recommendation**: **Downgrade to P2 for POC.** The direct `.rbxl` write path is sufficient. Rojo integration is a developer-experience improvement, not a functional requirement.

**In master plan?** Not mentioned. The README documents `.rbxl` output as the primary artifact.

---

#### 23. AssetUploader (P1) — IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Module | — | `modules/roblox_uploader.py` (217 lines) |
| Purpose | Upload meshes/textures to Roblox Asset API | Uploads .rbxl + textures to Open Cloud |

**Assessment**: Fully implemented. Uploads place files via `POST /v1/universes/{id}/places/{id}/versions` and textures via the Assets API with multipart form data. Handles API key validation, error cases, and rate limit awareness.

**In master plan?** Yes — listed in README as `roblox_uploader`.

---

#### 24. BuildOrchestrator (P0) — IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Module | — | `converter.py` (678 lines) |
| Purpose | Coordinate tool workflow | 5-phase sequential pipeline with CLI |

**Assessment**: Fully implemented as the `converter.py` orchestrator:
- Phase 1: Scene/prefab discovery
- Phase 2: Asset inventory + GUID resolution + prefab instance resolution
- Phase 3: Material mapping + code transpilation + mesh decimation
- Phase 4: RBXL assembly
- Phase 5: Upload + reporting

Complete with Click CLI, error collection, timing, and progress output. **No gap** for core orchestration.

**Differences from spec**: No trigger-based execution (CI/CD integration) or rollback on partial failures. These are operational concerns for production, not POC.

**In master plan?** Yes — `converter.py` is described in README and `material_converter_plan.md`.

---

#### 25. LoggingAndAudit (P1) — PARTIALLY IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Track conversions, errors, user overrides | `report_generator.py` (159 lines) |
| Outputs | Reports/dashboard | `conversion_report.json` + stdout summary |

**Assessment**: The conversion report captures:
- Asset counts by kind
- Material conversion stats (full/partial/unconvertible)
- Script transpilation results (succeeded/flagged/skipped)
- Scene stats (game objects, prefab instances, meshes)
- Errors and warnings
- Duration and output paths

Missing: real-time logging during conversion (currently uses `click.echo` for progress), persistent audit log across runs, dashboard/visualization.

**Recommendation**: **Adequate for POC.** Add structured logging (Python `logging` module) for production.

**In master plan?** Yes — listed in README as `report_generator`.

---

### Model Ops & LLM Integration

#### 26. PromptManager (P0 in spec) — NOT IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Store and manage prompt templates | N/A (single hardcoded prompt) |

**Needed?** The spec lists this as P0, but the current implementation only has ONE LLM call site (code transpilation). A prompt manager adds value when there are multiple prompt types that evolve over time.

**Assessment**: The single prompt in `_ai_transpile()` is:
```
"Convert the following Unity C# MonoBehaviour script to idiomatic Roblox Luau.
Output ONLY the Luau code, no explanations."
```

This is adequate for a single-purpose call. A template system becomes valuable when the tool adds more LLM call sites (asset QA, code review, UI generation, etc.).

**Recommendation**: **Downgrade to P1 for POC.** Not needed until there are 3+ different LLM prompt types.

**In master plan?** Not mentioned.

---

#### 27. BatchRequestHandler (P1) — NOT IMPLEMENTED

**Needed?** Potentially valuable for cost optimization on large projects. The spec estimates 200 calls × 500 tokens = ~$12, which is well within budget even without batching.

**Recommendation**: **Defer to post-POC.** Cost is low enough without batching.

---

#### 28. CacheManager (P1) — NOT IMPLEMENTED

**Needed?** Yes for iterative development workflows (re-running the converter on the same project). Avoids redundant LLM calls.

**Recommendation**: **Keep at P1.** Simple hash-based disk cache would be 50-100 lines.

**In master plan?** Not mentioned.

---

#### 29. CostEstimator (P2) — NOT IMPLEMENTED

**Needed?** Nice-to-have for budget planning.

**Recommendation**: **Defer.** P2 is correct.

---

#### 30. FineTuneManager (P2) — NOT IMPLEMENTED

**Needed?** Optional optimization for production.

**Recommendation**: **Defer.** P2 is correct. Claude API doesn't currently support fine-tuning.

---

#### 31. LLMMonitor (P1) — NOT IMPLEMENTED

**Needed?** For production operations, yes. For POC, the conversion report captures whether AI transpilation was used.

**Recommendation**: **Defer to post-POC.** The conversion report provides basic LLM usage tracking.

---

### Human-in-the-Loop

> **Update (2026-03-02):** The `/convert-unity` Claude Code skill now provides an interactive HITL workflow. It calls `convert_interactive.py` phase-by-phase, presenting results and decision points to the user between each step. This addresses the core intent of ReviewInterface, FeedbackIngestion, and HITL_JobScheduler without requiring a separate frontend.

#### 32. ReviewInterface (P0 in spec) — IMPLEMENTED via skill

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | UI for humans to review and adjust automated outputs | `/convert-unity` skill presents phase results and asks for decisions |

**Implementation**: The `/convert-unity` Claude Code skill serves as the review interface. After each conversion phase, it presents structured results (material conversion stats, flagged scripts with source/output, validation errors) and asks the user to accept, retry, edit, or skip. This is backed by `convert_interactive.py`, which outputs JSON that the skill parses and presents conversationally.

Key review points in the skill:
- Unconvertible materials → user decides: accept, provide manual mapping, or skip
- Flagged scripts (low confidence) → user sees original C# and generated Luau side by side
- Validation errors → user decides how to fix
- Mesh decimation warnings → user confirms quality tradeoffs

**Assessment**: The skill-based approach avoids the 5 pw frontend effort while providing a better experience than file-based review — the user gets guided decisions in context rather than reading JSON reports after the fact.

---

#### 33. FeedbackIngestion (P1) — PARTIALLY ADDRESSED via skill

The interactive skill naturally captures feedback: when a user rejects a transpiled script or provides manual corrections, that decision feeds into subsequent phases (e.g., the user can re-run transpilation with AI after reviewing rule-based output). Formal feedback persistence for model improvement is not yet implemented.

**Recommendation**: Adequate for current use. Persistent feedback logging can be added later.

---

#### 34. HITL_JobScheduler (P1) — IMPLEMENTED via skill

The `/convert-unity` skill acts as the job scheduler for human review. It tracks conversion state in `<output_dir>/.convert_state.json`, allows resuming partially completed conversions, and ensures flagged items are presented for review before proceeding to assembly.

**Assessment**: The confidence-based flagging mechanism (`flagged_for_review` on TranspiledScript) combined with the skill's interactive triage loop covers the spec's intent. The skill presents flagged scripts one by one (or in batch) and tracks which have been reviewed.

---

### Orchestration

#### 35. JobScheduler (P0) — IMPLEMENTED

| Aspect | Spec | Implementation |
|--------|------|----------------|
| Purpose | Coordinate execution of all tasks in correct order | `converter.py` sequential pipeline |

**Assessment**: Implemented as a linear 5-phase pipeline in `converter.py`. Not a generic job scheduler with DAG resolution, but achieves the spec's goal of running tasks in the correct order with dependency management.

**Differences**: No parallel execution (material mapping and code transpilation could run concurrently — noted in material_converter_plan.md but not implemented). No deadlock detection (not needed for sequential execution).

**Recommendation**: **Adequate for POC.** Parallel execution would improve performance on large projects.

**In master plan?** Yes — `converter.py` architecture described in material_converter_plan.md.

---

#### 36. RetryBackoff (P1) — NOT IMPLEMENTED

**Needed?** Yes for LLM API calls and Roblox API uploads, which can have transient failures.

**Assessment**: The current code catches exceptions broadly but doesn't retry. API rate limits and network timeouts will cause permanent failures.

**Recommendation**: **Keep at P1.** Simple exponential backoff decorator would be 20-30 lines.

**In master plan?** Not mentioned.

---

#### 37. AuditTrail (P2) — PARTIALLY IMPLEMENTED

**Assessment**: The conversion_report.json provides per-run traceability. Not an immutable append-only log, but covers the basic need.

**Recommendation**: **Adequate for POC.** P2 is correct.

---

## Functions in Codebase NOT in Spec

The codebase has significant functionality not captured in the function spec:

| Module | What it does | Why it matters |
|--------|-------------|----------------|
| `guid_resolver.py` (305 lines) | Bidirectional GUID ↔ asset-path index with chain resolution | Critical for Unity's GUID-based asset references. The spec lumps this into UnityProjectImporter but it deserves its own entry. |
| `scene_parser.py` (408 lines) | Parses `.unity` YAML scene files into SceneNode hierarchy | Core scene understanding. Not in the spec at all. Handles Unity's custom YAML format, classID/fileID resolution, Transform hierarchy. |
| `prefab_parser.py` (338 lines) | Parses `.prefab` files and resolves instances | Unity prefab system is fundamental. Not in spec. |
| `rbxl_writer.py` (241 lines) | Writes valid `.rbxl` XML files with SurfaceAppearance, MeshPart, scripts | The output format generator. Spec mentions Rojo but not direct .rbxl writing. |
| Prefab instance resolution (in converter.py) | Resolves PrefabInstance documents, applies m_Modifications | Complex Unity feature not mentioned in spec. |
| UNCONVERTED.md system | Smartdown reporting of unconvertible features | Not in spec — more granular than AssetQualityAssurance. |

**Recommendation**: The spec should be updated to include these as explicit functions, especially `SceneParser`, `PrefabParser`, `GuidResolver`, and `RbxlWriter`.

---

## Priority Reassessment for POC

Based on actual implementation status and POC acceptance criteria ("convert a small Unity game, ≤30% manual correction, no crashes, >70% logic match"):

### Revised P0 (Must-have for POC) — 8 functions, 7 implemented

| Function | Status | Gap |
|----------|--------|-----|
| UnityAssetExporter | Implemented | None |
| MeshSimplifier | Implemented | None |
| CSharpParser | Partial | AI path compensates; rule-based needs tree-sitter |
| APIMapper | Partial | AI path compensates; rule-based needs expansion |
| LLMTranslatorWrapper | Implemented | None |
| UnityProjectImporter | Implemented | None |
| BuildOrchestrator | Implemented | None |
| JobScheduler | Implemented | None |

### Revised P1 (Should-have for POC) — 12 functions, 3 implemented

| Function | Status | Gap |
|----------|--------|-----|
| MaterialMapper | Implemented | None |
| AssetUploader | Implemented | None |
| LoggingAndAudit | Partial | Adequate for POC |
| CodeValidator | NOT impl | Add Luau syntax check |
| AssetQualityAssurance | Partial | Adequate for POC |
| UIExtractor | NOT impl | Needed if target game has UI |
| LayoutTranslator | NOT impl | Needed if target game has UI |
| NetworkAnalyzer | NOT impl | Needed if target game is multiplayer |
| RemoteEventGenerator | NOT impl | Needed if target game is multiplayer |
| CacheManager | NOT impl | Improves iteration speed |
| RetryBackoff | NOT impl | Improves reliability |
| PromptManager | NOT impl | Needed when more LLM call sites added |

### Revised P2 (Nice-to-have) — 14 functions

TextureAtlasGenerator, AnimationRetargeter, AudioConverter, CodeQA, TestGenerator, UIGenerator, UIQA, ServerAuthorityMapper, RojoIntegrator, BatchRequestHandler, CostEstimator, FineTuneManager, LLMMonitor, AuditTrail.

*Note: ReviewInterface, FeedbackIngestion, and HITL_JobScheduler were previously listed here but are now addressed by the `/convert-unity` Claude Code skill.*

---

## Key Gaps to Address Before POC

1. **CodeValidator** — Add basic Luau syntax validation. Can use `luau-analyze` or at minimum check for unbalanced `end` keywords. ~50-100 lines. Prevents shipping broken scripts.

2. **CSharpParser (tree-sitter)** — The dependencies are already in `requirements.txt` but unused. Implementing AST-based parsing would significantly improve rule-based transpilation accuracy.

3. **APIMapper expansion** — Expand from 7 regex rules to a comprehensive mapping table. Can be a JSON data file loaded at startup. Critical for rule-based path.

4. **RetryBackoff** — Add exponential retry to `_ai_transpile()` and `roblox_uploader.py`. Simple decorator, high reliability impact.

5. **CacheManager** — Hash-based cache for LLM responses. Prevents redundant API calls during iterative development. Simple implementation.

---

## Functions Not Needed (Can Remove from Spec)

1. **TextureAtlasGenerator** (P0→Remove/P2) — Roblox uses per-MeshPart materials. Atlas packing adds complexity without Roblox-side benefit.

2. **RojoIntegrator** (P0→Remove/P2) — Direct `.rbxl` output is simpler and more portable than requiring Rojo toolchain.

3. **FineTuneManager** — Claude doesn't support fine-tuning. Would need to switch providers or use a different approach entirely.

4. **ReviewInterface** (P0→P2→Implemented) — Now provided by the `/convert-unity` Claude Code skill, which presents conversion results interactively and asks for human decisions at each phase.

---

## Cost Validation

The spec estimates 200 calls × 500 tokens × ($5+$25)/1M ≈ $12. This aligns with the implementation:
- code_transpiler.py: 1 Claude call per .cs file. A medium game with 200 scripts = 200 calls.
- Average C# script ≈ 50-200 lines ≈ 200-800 tokens input, 200-800 tokens output.
- At Claude Opus pricing: 200 × 500 × $15/$75 per 1M ≈ $1.50 input + $7.50 output ≈ **$9 per run**.
- With Claude Sonnet: significantly cheaper.

No additional LLM costs exist in the current implementation (material mapping and other modules are rule-based).

The cost estimate is **realistic and within budget**.
