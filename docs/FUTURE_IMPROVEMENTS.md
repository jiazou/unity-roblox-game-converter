# Future Improvements

## 1. Upload-then-patch anti-pattern (high impact)

**Problem:** Every pipeline run re-uploads all assets, and the .rbxl patching logic has grown to 4+ strategies of regex/XML matching accumulated over debugging sessions.

**Fix:** Separate asset upload from place assembly:
- Upload phase produces an **asset manifest** (`{filename: asset_id, content_hash: ...}`)
- Assembly phase reads the manifest and builds the .rbxl directly with correct asset IDs
- No post-hoc patching needed
- Manifest is persistent — only upload new/changed assets

**Files affected:** `modules/roblox_uploader.py` (patching logic), `convert_interactive.py` (upload command)

## 2. Monolithic roblox_uploader.py (1076 lines doing 6 jobs)

**Problem:** One file handles FBX→GLB conversion, texture injection, API uploading, .rbxl XML patching (4 strategies), Unity YAML parsing for mesh→material mapping, MeshLoader script generation, and username resolution.

**Fix:** Split into focused modules:
- `modules/asset_converter.py` — FBX→GLB, texture injection into glTF
- `modules/asset_uploader.py` — Open Cloud upload, async polling, caching
- `modules/rbxl_patcher.py` — XML patching strategies (if still needed after #1)
- `modules/mesh_loader_generator.py` — Luau MeshLoader script generation
- Keep `modules/roblox_uploader.py` as thin orchestrator

## 4. No upload cache / content-hash deduplication

**Problem:** 175 meshes × ~3 seconds each = 9+ minutes of API calls per run. No content hashing means identical assets get re-uploaded.

**Fix:**
- Hash each GLB/PNG/OGG file (SHA-256)
- Store `{content_hash: roblox_asset_id}` in a persistent manifest (JSON file in output dir)
- Before uploading, check if hash already exists → skip upload, reuse asset ID
- Invalidate only when source file changes

**Files affected:** `modules/roblox_uploader.py` (upload loops), `.convert_state.json` (or new manifest file)

## 3. Custom serializer vs rbx-dom/rbxmk (low priority)

**Problem:** `rbxl_binary_writer.py` (644 lines) reimplements Roblox's binary format. The research says rbx-dom is "the definitive industry standard." Our serializer misses internal properties (confirmed: MeshPart.MeshId set in XML is ignored by Studio).

**Current workaround:** InsertService:LoadAsset() at runtime bypasses the serializer for meshes entirely. The serializer only handles simple properties (scripts, lighting, spawn points) which it does correctly.

**Why low priority:** Since meshes load via InsertService, the serializer only writes the place shell. For that use case it works fine. Replacing with rbxmk adds a Go binary dependency for marginal benefit.

**If we do it:** Install rbxmk (`go install github.com/Anaminus/rbxmk@latest`), replace `rbxl_binary_writer.py` with a wrapper that calls `rbxmk run` with a Lua script to build the place file. This would correctly serialize all property types including MeshPart internals.

## 5. Replace rule-based C# transpiler with roblox-cs (medium priority)

**Problem:** Our rule-based transpiler produces ~30% error rate on complex scripts. The research identifies roblox-cs as "the most prominent attempt" — an AST-based transpiler using Roslyn that handles classes, inheritance, properties, and basic Unity API mapping.

**Current workaround:** AI-assisted transpilation via Claude API produces much better results (0% flagged rate). Rule-based is only used when AI is unavailable.

**If we do it:** Integrate roblox-cs as a .NET dependency. Run it as a subprocess for each .cs file. Fall back to our rule-based transpiler for files roblox-cs can't handle. Keep AI mode as the premium option.

**Note:** roblox-cs translates syntax but not Unity engine semantics. The architectural gap (MonoBehaviour lifecycle, component queries, Addressables) still requires manual redesign regardless of transpiler quality.
