# Convert Unity Project to Roblox

An interactive skill that guides the conversion of a Unity game project into a Roblox place (.rbxl). The conversion is non-linear — it requires human decisions at multiple checkpoints.

## Invocation

User-invocable: yes

## Instructions

You are orchestrating the Unity → Roblox game converter. This is a multi-phase pipeline where each phase may surface issues that need human judgment. Do NOT run the entire pipeline blindly — pause at each decision point and present findings to the user.

### Overview of Phases

1. **Discovery** — Scan the Unity project, parse scenes and prefabs
2. **Asset Inventory** — Catalog assets and resolve GUIDs
3. **Material Mapping** — Convert Unity materials to Roblox equivalents
4. **Code Transpilation** — Convert C# scripts to Luau
5. **Assembly** — Build the .rbxl file
6. **Upload** (optional) — Push to Roblox Cloud

### Prerequisites

Before running, install dependencies:
```bash
pip3 install -r requirements.txt --break-system-packages
```
Use `python3` (not `python`) — macOS does not ship `python`.

All commands require **two positional arguments**: `<unity_project_path>` and `<output_dir>`.

### Step-by-step Workflow

#### Step 0: Gather Inputs

Ask the user for:
- The path to the Unity project (the folder containing `Assets/`, `ProjectSettings/`, etc.)
- The desired output directory for the Roblox files
- Whether they want AI-assisted C# → Luau transpilation (requires Anthropic API key)

If the user provided these as arguments (e.g. `/convert-unity ./MyGame ./output`), parse them from the args instead of asking.

Validate that the Unity project path exists and contains an `Assets/` directory. If not, report the issue and ask the user to correct it.

#### Step 1: Discovery — Parse Scenes & Prefabs

```bash
python3 convert_interactive.py discover <unity_project_path> <output_dir>
```

This outputs a JSON summary to stdout. Present the results to the user:
- Number of scenes found and their names
- Number of prefabs found
- Number of material GUIDs referenced
- Any parse errors encountered

**Decision point:** If there are multiple scenes, ask which scenes to include. If there are parse errors, ask if the user wants to continue or investigate.

#### Step 2: Asset Inventory & GUID Resolution

```bash
python3 convert_interactive.py inventory <unity_project_path> <output_dir>
```

Present results:
- Total assets found, broken down by type (textures, meshes, audio, etc.)
- Total size
- GUID resolution stats (resolved, duplicates, orphans)

**Decision point:** If there are duplicate GUIDs or orphan .meta files, warn the user and ask how to proceed. If the project is very large, confirm they want to continue with full conversion.

#### Step 3: Material Mapping

```bash
python3 convert_interactive.py materials <unity_project_path> <output_dir> [--referenced-guids <comma-separated-guids>]
```

Present results:
- Total materials processed
- How many fully converted, partially converted, and unconvertible
- Texture operations performed
- If an UNCONVERTED.md was generated, read and summarize it for the user

**Decision point:** If there are unconvertible materials or partial conversions, present the specifics and ask the user:
- Accept as-is and continue?
- Want to provide manual mappings for specific materials?
- Skip certain materials entirely?

**Known issue — vertex colors:** Many Unity games (e.g., Trash Dash) use vertex-color-only shaders. Roblox does not support vertex colors, so these materials will appear flat/uncolored. The material mapper flags these as HIGH severity. There is no automated fix — the user must bake vertex colors into albedo textures manually in a 3D tool.

#### Step 4: Code Transpilation

```bash
python3 convert_interactive.py transpile <unity_project_path> <output_dir> [--use-ai] [--no-ai] [--api-key <key>]
```

**AI mode vs rule-based:**
- `--use-ai --api-key <key>` uses Claude for high-quality transpilation. Always prefer this when the user has a funded Anthropic API key.
- `--no-ai` uses the rule-based transpiler. Faster but produces many errors (residual C# curly braces, unbalanced blocks). Expect ~30% of scripts to have validation errors.
- If AI mode fails with "credit balance too low" or 401, the key has no credits. Do NOT retry the same key — inform the user and offer `--no-ai` as fallback.

Present results:
- Total scripts found
- How many succeeded vs flagged for review
- Strategy used (AI vs rule-based) per script

**Decision point — this is the most interactive step:**
- For each flagged script (low confidence), show the user:
  - The original C# source (abbreviated if long)
  - The generated Luau code
  - The specific warnings/issues
  - Ask: Accept, Retry with AI, Edit manually, or Skip?
- If there are many flagged scripts (>5), offer a batch option: "Accept all", "Skip all flagged", or "Review one by one"
- For scripts with residual C# patterns (class keywords, curly braces), highlight these as needing attention

After the user reviews flagged scripts, run Luau validation:
```bash
python3 convert_interactive.py validate <output_dir>
```

Report validation errors and let the user decide how to handle them.

**Known issue — false positive curly-brace errors:** The validator flags valid Luau table constructors (`{}`) as C# curly braces. If AI transpilation was used and the scripts look correct, these errors are noise. Inform the user and proceed.

#### Step 5: Assembly — Build .rbxl

```bash
python3 convert_interactive.py assemble <unity_project_path> <output_dir> [--decimate] [--state-file <path>]
```

Present results:
- Number of parts written
- Number of scripts embedded
- Output file path and size
- Any warnings from the writer

**Known issues:**
- **FBX meshes skipped**: `trimesh` does not support `.fbx` format. All FBX meshes will be skipped for decimation and referenced by local filesystem path. The user will need to import FBX files manually into Roblox Studio.
- **SurfaceAppearance may be missing**: The assembly phase relies on MeshRenderer components being present on scene nodes. If most meshes are inside prefab instances, the prefab resolution may not fully extract MeshRenderer data, resulting in 0 SurfaceAppearance items. The upload patcher (Step 6) compensates by scanning the Unity project for mesh→material relationships.

**Decision point:** If mesh decimation was enabled and some meshes were significantly reduced or skipped, present the details and ask if the user wants to adjust quality settings and re-run.

#### Step 6: Upload (Optional)

Ask the user if they want to upload to Roblox Cloud. If yes, they need:
- Roblox Open Cloud API key (with `asset:read`, `asset:write`, and `place:write` scopes)
- Universe ID and Place ID (must already exist — the API cannot create them)
- Creator ID (their Roblox user ID or group ID)

**Important — place must exist first:** The Roblox Place Publishing API only uploads to existing places. If the user just created the game, they must publish an initial version from Roblox Studio before the API will accept uploads. A persistent HTTP 409 "Server is busy" error means the place needs this initial publish.

**Important — look up numeric user ID:** If the user provides a Roblox username, resolve it to a numeric ID:
```bash
curl -s -X POST "https://users.roblox.com/v1/usernames/users" \
  -H "Content-Type: application/json" \
  -d '{"usernames": ["<username>"]}'
```

The upload step handles four operations in order:

1. **Textures** — PNGs from `<output_dir>/textures/` uploaded as Decal assets
2. **Sprites** — Sliced sprite PNGs from `<output_dir>/sprites/` uploaded as Decal assets
3. **Audio** — Audio files from `<output_dir>/audio/` uploaded as Audio assets
4. **Patch & Upload Place** — The .rbxl is patched with `rbxassetid://` URLs, converted from XML to binary format, then uploaded

**Critical:** The Roblox asset upload API is **asynchronous**. The initial POST returns an `operationId` with `done: false`. The uploader polls the operation until complete to get the actual `assetId`. This is handled automatically.

**Critical:** The Roblox Place Publishing API only accepts **binary .rbxl** format, not XML. The uploader automatically converts XML → binary using `modules/rbxl_binary_writer.py`.

```bash
python3 convert_interactive.py upload <output_dir> [--roblox-api-key <key>] [--universe-id <id>] [--place-id <id>] [--creator-id <id>] [--creator-type User|Group]
```

Present results:
- Number of textures/sprites/audio uploaded and their asset IDs
- Whether the .rbxl was patched with the new asset IDs
- Place upload success/failure and version number

**Asset patching details:** The patcher uses three strategies to inject `rbxassetid://` URLs:
1. Replaces `rbxassetid://` placeholders and `-- TODO: upload` comments
2. Replaces local filesystem paths in Content elements by matching filenames
3. Injects SurfaceAppearance children on MeshParts by scanning the Unity project for mesh→material relationships (MeshFilter + MeshRenderer GUID pairs in .prefab/.unity files)

**Decision point:** If some asset uploads fail (rate limits, size limits, format issues), ask the user:
- Retry failed uploads?
- Continue without those assets (they'll show as placeholder in-game)?
- Abort and fix the issues first?

After a successful upload, the .rbxl in the output directory will have been rewritten with real `rbxassetid://` URLs, so the user can also open it in Roblox Studio with working references.

#### Step 7: Final Report

```bash
python3 convert_interactive.py report <output_dir>
```

Read the generated report and present a summary to the user. Highlight:
- Overall success/failure
- Key metrics (assets, materials, scripts, parts)
- Any remaining warnings or errors
- Suggestions for manual follow-up (flagged scripts, unconverted materials)

### Error Handling

- If any phase command fails, show the error to the user and ask how to proceed
- Offer to retry, skip the phase, or abort the conversion
- Never silently swallow errors — every issue is a potential decision point
- If a command outputs a YAML parse warning to stderr before the JSON (e.g., "Failed to parse YAML in UIRenderer.asset"), strip it before parsing JSON

### State Management

The interactive pipeline writes intermediate state to `<output_dir>/.convert_state.json`. This allows:
- Resuming a partially completed conversion
- Re-running individual phases with different settings
- If state exists from a previous run, ask the user if they want to resume or start fresh
- The `mesh_texture_map` and `unity_project_path` fields in state are used by the upload patcher

### Tips for the Operator (Claude)

- Be concise in summaries but thorough when presenting decision points
- When showing code (C# or Luau), use fenced code blocks with language tags
- For large lists (many materials, many scripts), summarize counts first, then offer to drill into specifics
- Remember the user's earlier decisions — if they said "accept all partial materials", don't re-ask for the same category
- If the Unity project is a well-known game template (e.g., Trash Dash), mention that you recognize it and highlight known conversion considerations from the docs
- If an API key fails, do NOT retry the same key more than once with the same error — inform the user
- Parse JSON output carefully: some commands emit warnings to stderr before the JSON on stdout. Use a Python one-liner to extract just the JSON, or redirect stderr
- When presenting upload results, always show the count of asset IDs actually captured (not just uploads attempted), as async operations may fail silently
