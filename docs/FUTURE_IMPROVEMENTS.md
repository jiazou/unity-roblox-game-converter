# Future Improvements

## Quick Wins

### QW-1. Conversion report with warnings for silently dropped components (high impact)

**Problem:** The pipeline recognizes 30+ Unity component types (Animator, NavMeshAgent, Terrain, CharacterController, LineRenderer, TrailRenderer, Cloth, WindZone, etc.) but silently drops them during conversion. Users have no way to know what's missing from their converted game.

**Fix:** Generate a structured conversion report at the end of assembly that lists:
- Every component type encountered and how it was handled (converted / partially converted / dropped)
- Per-object warnings: "GameObject 'Enemy' has NavMeshAgent — AI navigation not converted"
- Summary counts: "147 components converted, 23 dropped (12 Animator, 8 NavMeshAgent, 3 Terrain)"
- Actionable suggestions: "Consider porting Animator behavior manually via Roblox AnimationController"

**Files affected:** `modules/conversion_helpers.py` (collect warnings during `node_to_part`), `modules/report_generator.py` (format report), `convert_interactive.py` / `converter.py` (surface report)

### QW-2. Transpiler warnings for inheritance chains and LINQ (high impact)

**Problem:** When a C# class inherits from a custom base class, only the child class methods are transpiled — base class methods are silently lost. LINQ expressions (`Where`, `Select`, `FirstOrDefault`) produce broken Luau. Users don't know these patterns failed.

**Fix:** During transpilation, detect and flag:
- Classes that extend anything other than MonoBehaviour/ScriptableObject — warn that base class logic is not included
- LINQ method chains — warn that these need manual rewriting
- Complex generic types beyond `GetComponent<T>` — warn about unsupported generics
- Networking attributes (`[Command]`, `[ClientRpc]`, `[SyncVar]`) — warn that multiplayer logic is not converted

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

**Fix:**
- Extract AnimationClip keyframe data from Unity `.anim` files
- Map Unity Humanoid bone names to Roblox R15 rig parts
- Convert keyframe curves to Roblox KeyframeSequence format
- Map Animator state machine to a Luau script that drives AnimationController
- Handle blend trees as weighted animation blending in Luau

**Complexity:** Very high — bone name mapping is non-trivial, Unity Mecanim state machines are complex, and blend tree math needs faithful reproduction.

**Files affected:** New `modules/animation_converter.py`, `modules/rbxl_writer.py` (AnimationController instances)

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

### IP-2. Monolithic roblox_uploader.py (1076 lines doing 6 jobs)

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

### IP-5. Replace rule-based C# transpiler with roblox-cs (medium priority)

**Problem:** Our rule-based transpiler produces ~30% error rate on complex scripts. The research identifies roblox-cs as "the most prominent attempt" — an AST-based transpiler using Roslyn that handles classes, inheritance, properties, and basic Unity API mapping.

**Current workaround:** AI-assisted transpilation via Claude API produces much better results (0% flagged rate). Rule-based is only used when AI is unavailable.

**If we do it:** Integrate roblox-cs as a .NET dependency. Run it as a subprocess for each .cs file. Fall back to our rule-based transpiler for files roblox-cs can't handle. Keep AI mode as the premium option.

**Note:** roblox-cs translates syntax but not Unity engine semantics. The architectural gap (MonoBehaviour lifecycle, component queries, Addressables) still requires manual redesign regardless of transpiler quality.
