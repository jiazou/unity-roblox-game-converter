# Project Problems Analysis

Comprehensive review of the Unity-to-Roblox game converter, organized from high-level architectural issues down to per-module bugs and concerns.

---

## 1. High-Level Architectural Problems

### 1.1 Massive Redundant Re-parsing in Interactive Mode

**Severity: HIGH** | **Files: `convert_interactive.py`**

The `assemble` phase (line 525–784) and `report` phase (line 866–959) re-parse the *entire* Unity project from scratch — scenes, prefabs, GUID index, materials, and transpilation are all re-run. This means:

- A project with 100 scenes and 500 materials gets parsed 3+ times across a single interactive conversion.
- The `assemble` phase re-runs material mapping (expensive PIL/texture operations) and transpilation even though `materials` and `transpile` phases already produced these results.
- The `report` phase does it *again*.

The `discover` phase also parses every scene *twice* (lines 148–159 then 179–184) — once to build `parsed_scenes_info` and once to collect `all_mat_guids`.

**Root cause:** The interactive CLI was designed to be "stateless" per-phase, but the state file (`.convert_state.json`) only stores metadata, not the actual parsed objects. This forces expensive re-computation.

### 1.2 `conversion_helpers.py` Violates the No-Cross-Import Rule

**Severity: MEDIUM** | **Files: `modules/conversion_helpers.py`**

The CLAUDE.md states: *"No module imports another module — all wiring happens in the orchestrators."* However, `conversion_helpers.py` imports 8 other modules (scene_parser, material_mapper, code_transpiler, rbxl_writer, guid_resolver, prefab_parser, mesh_decimator, report_generator). It acts as a second orchestrator hidden inside `modules/`.

This creates a fragile dependency graph where adding any import of `conversion_helpers` from another module would cause a circular import. It also makes the dependency rules unclear — is `conversion_helpers` an orchestrator or a module?

### 1.3 `import shutil` Inside Function Body

**Severity: LOW** | **Files: `converter.py:354`, `convert_interactive.py:707`**

Both orchestrators have `import shutil` inlined at the point of use instead of at the top of the file. This is a PEP 8 violation and makes dependency scanning harder. It's also inconsistent — every other import is at the top.

### 1.4 No Packaging / Entry Point Configuration

**Severity: MEDIUM** | **Files: project root**

There is no `setup.py`, `pyproject.toml`, or `setup.cfg`. The project can only be run via `python converter.py` or `python convert_interactive.py`. This means:

- No `pip install -e .` for development
- No CLI entry points (e.g. `unity2roblox` command)
- No version tracking
- Dependencies in `requirements.txt` have no version pins (except `Pillow>=10.0.0` and `trimesh>=4.0.0`), risking breaking upgrades

### 1.5 Anthropic Model Hardcoded to Nonexistent Version

**Severity: HIGH** | **Files: `config.py:24`**

`ANTHROPIC_MODEL` is set to `"claude-opus-4-5"`. The actual model ID should be `"claude-opus-4-5-20250120"` or similar dated variant, or `"claude-sonnet-4-5-20250514"`. Using a bare `"claude-opus-4-5"` may work if the API resolves it, but it's fragile and may break or silently route to a different model.

### 1.6 Placeholder API Key Shipped in Config

**Severity: MEDIUM** | **Files: `config.py:23`**

`ANTHROPIC_API_KEY` defaults to `"sk-ant-PLACEHOLDER"`. While the uploader validates against known placeholders, the transpiler does not — it would attempt an API call with this placeholder key and get a 401 error at runtime rather than failing fast with a clear message.

---

## 2. Data Flow & Logic Problems

### 2.1 Silent Data Loss from YAML Parse Failures

**Severity: HIGH** | **Files: `modules/unity_yaml_utils.py`, `modules/scene_parser.py`**

`parse_documents()` silently skips YAML documents that fail to parse. A corrupted or unusual document is logged at debug level but the GameObjects it contains are simply absent from the output. Downstream code has no way to know that 10% of the scene was silently dropped.

The error count is not propagated to the report. Users could get a "successful" conversion that's missing major chunks of their game.

### 2.2 `assemble` Phase Ignores User-Edited Scripts

**Severity: HIGH** | **Files: `convert_interactive.py:573-580`**

The `assemble` phase re-runs `code_transpiler.transpile_scripts()` from the original C# source (line 573), completely ignoring the Luau scripts saved to `<output_dir>/scripts/` during the `transpile` phase. If a user or the skill edited a flagged script between `transpile` and `assemble`, those edits are lost.

The `use_ai=False` override (line 575) also means assembly always uses rule-based transpilation, even if the user chose AI transpilation in the `transpile` phase.

### 2.3 Audio File Discovery via `rglob` is Fragile

**Severity: MEDIUM** | **Files: `converter.py:373`, `convert_interactive.py:727`**

When resolving serialized AudioClip references, the code does `unity_path.rglob(audio_filename)`. This:

- Could match files in wrong directories (e.g. `Library/` or `Temp/`)
- Is O(n) filesystem walk per audio reference
- Takes the first match (`matches[0]`) without verifying it's the correct asset
- Doesn't use the GUID index that was already built for exactly this purpose

### 2.4 Material GUID Lookup Logic Iterates All GUIDs

**Severity: LOW** | **Files: `converter.py:297-303`, `convert_interactive.py:651-657`**

The GUID-to-material-def mapping iterates `guid_index.guid_to_entry.items()` (all GUIDs in the project) and checks each against `mat_result.roblox_defs`. This is O(n*m) where n=total GUIDs and m=materials. For large projects this could be slow. A reverse lookup from `roblox_defs` keys back through the GUID index would be more efficient.

### 2.5 `referenced_guids or None` Passes Empty Set as None

**Severity: LOW** | **Files: `converter.py:183`, `convert_interactive.py:304`**

`referenced_guids or None` evaluates to `None` when `referenced_guids` is an empty set, which tells `map_materials` to process *all* materials rather than *no* materials. An empty set should mean "nothing referenced, skip material processing" but instead it means "process everything."

---

## 3. Module-Level Problems

### 3.1 `code_transpiler.py` — Script Type Classification is Naive

**Severity: MEDIUM**

Script type (Script vs LocalScript vs ModuleScript) is classified purely by which API calls appear in the source. A script that only uses `print()` defaults to `Script` (server-side), which would fail silently if the script was meant to be client-side. The classification also doesn't consider Unity's execution context (Editor scripts, ScriptableObjects, etc.).

### 3.2 `code_transpiler.py` — AI Transpilation Has No Token Budget Guard

**Severity: MEDIUM**

When `use_ai=True`, each C# file is sent to Claude with `max_tokens=4096`. For large C# files (1000+ lines), the response may be truncated at 4096 tokens, producing incomplete Luau. There's no check for truncation (e.g. inspecting `stop_reason`) and no splitting of large files.

### 3.3 `code_transpiler.py` — Tree-sitter Error Recovery is Silent

**Severity: LOW**

If tree-sitter parsing produces an AST with `ERROR` nodes (partial parse), the `_LuauEmitter` doesn't detect or report these. Malformed C# syntax silently produces malformed Luau.

### 3.4 `material_mapper.py` — No Texture Operation Rollback

**Severity: MEDIUM**

Texture operations (resize, channel extract, bake AO, etc.) write files to the output directory. If the pipeline fails partway through, partial/corrupt texture files are left behind. Re-running the pipeline may skip operations if the output file already exists (filename collision), leading to stale data.

### 3.5 `material_mapper.py` — Imports `config` Directly

**Severity: LOW**

Unlike other modules which receive configuration values as parameters, `material_mapper.py` imports `config` directly. This makes it harder to test with different configurations and violates the pattern used by the rest of the pipeline.

### 3.6 `rbxl_writer.py` — No XML Escaping of Script Source

**Severity: MEDIUM**

Luau script source is embedded inside `<ProtectedString>` XML elements. If the Luau source contains XML-special characters (`<`, `>`, `&`), the lxml/minidom serializer should handle escaping — but the code uses string concatenation in some paths. If any path bypasses proper XML serialization, it could produce corrupt `.rbxl` files.

### 3.7 `roblox_uploader.py` — Multipart Boundary Not RFC-Compliant

**Severity: LOW**

The multipart boundary is generated as `f"----UnityRobloxConverter{int(time.time() * 1000)}"`. If two uploads happen in the same millisecond (e.g. parallel texture uploads in a future version), they'd share a boundary. The boundary also isn't checked against the file content — if the boundary string appears in a binary file, the upload would be malformed.

### 3.8 `roblox_uploader.py` — Image Upload Always Uses "Decal" Asset Type

**Severity: MEDIUM**

`_upload_image_asset` hardcodes `"assetType": "Decal"` for all image uploads. SurfaceAppearance textures (normal maps, metalness maps) should arguably be uploaded as different asset types or with different metadata. This may cause issues with Roblox's content moderation or asset categorization.

### 3.9 `roblox_uploader.py` — Text Fallback Patches Script Source

**Severity: MEDIUM**

`_patch_rbxl_asset_ids_text()` does global string replacement across the entire `.rbxl` XML content. If a Luau script contains a string literal like `"rbxassetid://myTexture.png"`, the text fallback would incorrectly replace it. The XML-aware path (lines 340-381) correctly limits patching to `<Content>` and `<url>` tags, but the fallback has no such guard.

### 3.10 `mesh_decimator.py` — Quality Floor Can Prevent Compliance

**Severity: LOW**

If a mesh has 50,000 faces and `MESH_QUALITY_FLOOR=0.6`, the minimum allowed is 30,000 faces — still above the 10,000 Roblox limit. The mesh will be decimated to 30,000 faces but still non-compliant. The code doesn't warn about this case.

### 3.11 `code_validator.py` — Only Checks Luau Syntax, Not Semantics

**Severity: LOW**

The validator checks block balance and residual C# syntax, but doesn't verify that Roblox API calls are valid (e.g. `workspace:FindFirstChild` vs `workspace.FindFirstChild`). A script could pass validation but fail at runtime.

### 3.12 `guid_resolver.py` — First GUID Wins on Duplicates

**Severity: LOW**

When duplicate GUIDs are found, the first occurrence wins. The "correct" asset depends on Unity's own resolution order, which may not match filesystem traversal order. This could resolve to the wrong asset in projects with GUID conflicts.

---

## 4. Test Suite Problems

### 4.1 No Integration Tests for AI Transpilation Path

**Severity: HIGH**

The AI transpilation path (which calls the Claude API) is only tested with mocks. There are no tests that verify:
- The prompt format sent to Claude
- Handling of truncated responses
- Handling of API errors (rate limits, invalid key)
- Whether the parsed response actually produces valid Luau

### 4.2 Network/Upload Tests Are Fully Mocked

**Severity: MEDIUM**

`test_roblox_uploader.py` mocks all HTTP calls. There are no tests for:
- Rate limiting behavior (429 responses with retry)
- Partial upload failures (some textures succeed, some fail)
- Timeout handling
- Actual multipart form data construction validity
- Response parsing for different Roblox API versions

### 4.3 No Large-Scale / Stress Tests

**Severity: MEDIUM**

All test fixtures use minimal data (1-3 scenes, 1-5 materials, 1-3 scripts). There are no tests for:
- Projects with 100+ scenes
- Projects with 1000+ materials
- Projects with deeply nested hierarchies (50+ levels)
- Very large C# files (5000+ lines)
- Memory usage under load

### 4.4 Material Texture Operations Not Pixel-Verified

**Severity: MEDIUM**

Material mapper tests check that texture operations are *queued* but don't verify the pixel output. A bug in channel extraction or normal map inversion would not be caught.

### 4.5 Duplicate Scene Parse in `discover` Phase Not Tested

**Severity: LOW**

The bug where `discover` parses scenes twice (section 1.1) is not caught by tests because tests use small inputs where the performance impact is invisible.

---

## 5. Configuration & Operational Problems

### 5.1 No Logging Configuration

**Severity: MEDIUM**

Modules use `logging.getLogger(__name__)` but neither orchestrator configures the logging system (no `logging.basicConfig()` or handler setup). All log messages are silently dropped unless the caller configures logging externally. The `click.echo()` messages in the orchestrators are the only user-visible output.

### 5.2 No Graceful Ctrl+C Handling

**Severity: LOW**

Neither orchestrator handles `KeyboardInterrupt`. If a user cancels during material processing or mesh decimation, partial output files may be left in an inconsistent state. The interactive mode's state file won't record the interrupted phase.

### 5.3 `.asset` Extension Mapped to `"unknown"` Kind

**Severity: LOW** | **Files: `config.py:68`**

Unity `.asset` files are mapped to `"unknown"` in `ASSET_EXT_TO_KIND`, but `scriptable_object_converter.py` specifically processes `.asset` files. This means ScriptableObject assets are categorized as "unknown" in the asset manifest and report, which is misleading.

### 5.4 No Input Validation Before Pipeline Start

**Severity: LOW**

Neither orchestrator checks:
- That the Unity project has an `Assets/` directory
- That the output directory is writable
- That required tools (tree-sitter, PIL, trimesh) are available before starting
- Available disk space for output

Failures surface late in the pipeline with less helpful error messages.

### 5.5 `pytest` Not Listed in `requirements.txt`

**Severity: LOW**

The test runner (`pytest`) is not in `requirements.txt`. A developer cloning the project wouldn't know which test dependencies are needed. There's also no `requirements-dev.txt` or `[dev]` extras.

---

## 6. Security Concerns

### 6.1 YAML Loading Without Safe Loader

**Severity: MEDIUM** | **Files: `modules/unity_yaml_utils.py`, `modules/material_mapper.py`**

Need to verify whether `yaml.safe_load()` or `yaml.load(Loader=SafeLoader)` is used everywhere. Unity YAML files from untrusted sources could exploit `yaml.load()` (without safe loader) for arbitrary code execution.

### 6.2 Filename Injection in Multipart Upload

**Severity: LOW** | **Files: `modules/roblox_uploader.py:213`**

The upload filename is taken directly from `image_path.name` and embedded in a multipart header without sanitization: `filename="{image_path.name}"`. A file named `foo"; rm -rf /` would produce a malformed header. While this is unlikely to be exploitable via HTTP, it could cause upload failures.

### 6.3 XML Parsing of Untrusted `.rbxl` in Patching

**Severity: LOW** | **Files: `modules/roblox_uploader.py:341`**

`ET.parse(rbxl_path)` is used without defusing XML attacks (XXE, billion laughs). The `.rbxl` is self-generated so the risk is minimal, but if the file was tampered with between write and patch, it could be exploited. The `# noqa: S314` comment acknowledges this.
